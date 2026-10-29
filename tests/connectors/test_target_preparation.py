
import unittest
from unittest.mock import MagicMock, patch

from app.models.connection import ConnectionMetadata
from app.connectors.postgres.adapter import PostgreSQLConnector
from app.connectors.sqlserver.adapter import SQLServerConnector


def make_metadata(connector_code: str) -> ConnectionMetadata:
    return ConnectionMetadata(
        connection_id=1,
        connection_name="Unit Test Connection",
        connector_id=1,
        connector_code=connector_code,
        connector_name=connector_code,
        connector_version_id=1,
        connector_version="1.0",
        host_name="localhost",
        port_no=5432,
        database_name="unit_test_db",
        endpoint_url=None,
        credential_id=None,
        connection_role_code="TARGET",
        connect_timeout_seconds=5,
        command_timeout_seconds=10,
        parameters={},
    )


def make_mock_connection():
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    connection.cursor.return_value.__exit__.return_value = False
    return connection, cursor


class TargetPreparationTests(unittest.TestCase):

    def setUp(self):
        self.pg = PostgreSQLConnector(
            make_metadata("POSTGRESQL_CONNECTOR")
        )
        self.sqlserver = SQLServerConnector(
            make_metadata("SQL_SERVER_CONNECTOR")
        )

    def test_postgres_type_mapping(self):
        self.assertEqual(
            self.pg._target_column_type("integer"), "INTEGER"
        )
        self.assertEqual(
            self.pg._target_column_type("boolean"), "BOOLEAN"
        )
        self.assertEqual(
            self.pg._target_column_type("timestamp with time zone"),
            "TIMESTAMPTZ",
        )

    def test_postgres_preserves_supported_type_attributes(self):
        self.assertEqual(
            self.pg._target_column_type(
                "character varying",
                {"character_maximum_length": 64},
            ),
            "VARCHAR(64)",
        )
        self.assertEqual(
            self.pg._target_column_type(
                "numeric",
                {"numeric_precision": 12, "numeric_scale": 4},
            ),
            "NUMERIC(12, 4)",
        )
        self.assertEqual(
            self.pg._target_column_type(
                "timestamp without time zone",
                {"datetime_precision": 3},
            ),
            "TIMESTAMP(3)",
        )

    def test_sqlserver_type_mapping(self):
        self.assertEqual(
            self.sqlserver._target_column_type("integer"), "INT"
        )
        self.assertEqual(
            self.sqlserver._target_column_type("boolean"), "BIT"
        )
        self.assertEqual(
            self.sqlserver._target_column_type("uuid"),
            "UNIQUEIDENTIFIER",
        )

    def test_sqlserver_preserves_supported_type_attributes(self):
        self.assertEqual(
            self.sqlserver._target_column_type(
                "varchar",
                {"character_maximum_length": 64},
            ),
            "VARCHAR(64)",
        )
        self.assertEqual(
            self.sqlserver._target_column_type(
                "decimal",
                {"numeric_precision": 12, "numeric_scale": 4},
            ),
            "DECIMAL(12, 4)",
        )
        self.assertEqual(
            self.sqlserver._target_column_type(
                "datetime2",
                {"datetime_precision": 3},
            ),
            "DATETIME2(3)",
        )

    def test_postgres_rejects_unsupported_type(self):
        with self.assertRaises(ValueError):
            self.pg._target_column_type("unsupported_custom_type")

    def test_sqlserver_rejects_unsupported_type(self):
        with self.assertRaises(ValueError):
            self.sqlserver._target_column_type("unsupported_custom_type")

    def test_postgres_rejects_empty_columns(self):
        with self.assertRaises(ValueError):
            self.pg.create_table("staging", "customers", [])

    def test_sqlserver_rejects_empty_columns(self):
        with self.assertRaises(ValueError):
            self.sqlserver.create_table("staging", "customers", [])

    def test_postgres_rejects_missing_schema(self):
        with patch.object(self.pg, "schema_exists", return_value=False):
            with self.assertRaises(LookupError):
                self.pg.create_table(
                    "missing_schema",
                    "customers",
                    [{"column_name": "id", "data_type": "integer"}],
                )

    def test_sqlserver_rejects_missing_schema(self):
        with patch.object(
            self.sqlserver, "schema_exists", return_value=False
        ):
            with self.assertRaises(LookupError):
                self.sqlserver.create_table(
                    "missing_schema",
                    "customers",
                    [{"column_name": "id", "data_type": "integer"}],
                )

    def test_postgres_does_not_recreate_existing_table(self):
        connection, cursor = make_mock_connection()
        self.pg._connection = connection

        with (
            patch.object(self.pg, "schema_exists", return_value=True),
            patch.object(self.pg, "table_exists", return_value=True),
        ):
            self.pg.create_table(
                "staging",
                "customers",
                [{"column_name": "id", "data_type": "integer"}],
            )

        cursor.execute.assert_not_called()

    def test_sqlserver_does_not_recreate_existing_table(self):
        connection, cursor = make_mock_connection()
        self.sqlserver._connection = connection

        with (
            patch.object(
                self.sqlserver, "schema_exists", return_value=True
            ),
            patch.object(
                self.sqlserver, "table_exists", return_value=True
            ),
        ):
            self.sqlserver.create_table(
                "staging",
                "customers",
                [{"column_name": "id", "data_type": "integer"}],
            )

        cursor.execute.assert_not_called()

    def test_postgres_generates_create_table_statement(self):
        connection, cursor = make_mock_connection()
        self.pg._connection = connection

        columns = [
            {
                "column_name": "name",
                "data_type": "text",
                "ordinal_position": 2,
                "is_nullable": "YES",
            },
            {
                "column_name": "id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
            },
        ]

        with (
            patch.object(self.pg, "schema_exists", return_value=True),
            patch.object(self.pg, "table_exists", return_value=False),
        ):
            self.pg.create_table("staging", "customers", columns)

        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args.args[0]

        self.assertIn("CREATE TABLE", sql.upper())
        self.assertIn('"id" INTEGER NOT NULL', sql)
        self.assertIn('"name" TEXT', sql)
        self.assertLess(sql.index('"id"'), sql.index('"name"'))

    def test_sqlserver_generates_create_table_statement(self):
        connection, cursor = make_mock_connection()
        connection.closed = False
        self.sqlserver._connection = connection

        columns = [
            {
                "column_name": "name",
                "data_type": "text",
                "ordinal_no": 2,
                "is_nullable": True,
            },
            {
                "column_name": "id",
                "data_type": "integer",
                "ordinal_no": 1,
                "is_nullable": False,
            },
        ]

        with (
            patch.object(
                self.sqlserver, "schema_exists", return_value=True
            ),
            patch.object(
                self.sqlserver, "table_exists", return_value=False
            ),
        ):
            self.sqlserver.create_table("staging", "customers", columns)

        cursor.execute.assert_called_once()
        sql = cursor.execute.call_args.args[0]

        self.assertIn("CREATE TABLE", sql.upper())
        self.assertIn("[id] INT NOT NULL", sql)
        self.assertIn("[name] NVARCHAR(MAX)", sql)
        self.assertLess(sql.index("[id]"), sql.index("[name]"))

    def test_postgres_generates_column_evolution_statements(self):
        connection, cursor = make_mock_connection()
        self.pg._connection = connection

        self.pg.add_column(
            "warehouse",
            "employee",
            {
                "column_name": "customer_address",
                "data_type": "text",
                "is_nullable": "YES",
            },
        )
        self.pg.drop_column("warehouse", "employee", "employee_role")

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertIn(
            'ALTER TABLE "warehouse"."employee" ADD COLUMN '
            '"customer_address" TEXT;',
            statements[0],
        )
        self.assertEqual(
            statements[1],
            'ALTER TABLE "warehouse"."employee" DROP COLUMN "employee_role";',
        )

    def test_sqlserver_generates_column_evolution_statements(self):
        connection, cursor = make_mock_connection()
        connection.closed = False
        self.sqlserver._connection = connection

        self.sqlserver.add_column(
            "warehouse",
            "employee",
            {
                "column_name": "customer_address",
                "data_type": "text",
                "is_nullable": "YES",
            },
        )
        self.sqlserver.drop_column("warehouse", "employee", "employee_role")

        statements = [call.args[0] for call in cursor.execute.call_args_list]
        self.assertEqual(
            statements[0],
            "ALTER TABLE [warehouse].[employee] ADD "
            "[customer_address] NVARCHAR(MAX);",
        )
        self.assertEqual(
            statements[1],
            "ALTER TABLE [warehouse].[employee] DROP COLUMN [employee_role];",
        )


if __name__ == "__main__":
    unittest.main()
