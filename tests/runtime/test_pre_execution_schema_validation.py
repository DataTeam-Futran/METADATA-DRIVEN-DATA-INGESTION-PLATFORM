import unittest
from types import SimpleNamespace

from app.runtime.pre_execution_validator import PreExecutionValidator


class FakeSchemaConnector:
    def __init__(self, columns, exists=True):
        self.columns = [dict(column) for column in columns]
        self.exists = exists
        self.created_columns = None
        self.commit_count = 0
        self.rollback_count = 0
        self.create_mismatched_schema = False
        self._transaction_snapshot = None

    def connect(self):
        return None

    def close(self):
        return None

    def table_exists(self, _schema_name, _table_name):
        return self.exists

    def list_columns(self, _schema_name, _table_name):
        return [dict(column) for column in self.columns]

    def begin_transaction(self):
        self._transaction_snapshot = (
            [dict(column) for column in self.columns],
            self.exists,
        )

    def create_table(self, _schema_name, _table_name, columns):
        self.created_columns = [dict(column) for column in columns]
        self.columns = [dict(column) for column in columns]
        if self.create_mismatched_schema:
            self.columns[-1]["data_type"] = "varchar"
        self.exists = True

    def commit(self):
        self.commit_count += 1
        self._transaction_snapshot = None

    def rollback(self):
        self.rollback_count += 1
        if self._transaction_snapshot is not None:
            self.columns, self.exists = self._transaction_snapshot
            self._transaction_snapshot = None


class PreExecutionSchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.source_columns = [
            {
                "column_name": "id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
            },
            {
                "column_name": "name",
                "data_type": "text",
                "ordinal_position": 2,
                "is_nullable": "YES",
            },
        ]
        self.mapping = [
            SimpleNamespace(
                source_field_name=column["column_name"],
                target_field_name=column["column_name"],
                ordinal_no=index,
            )
            for index, column in enumerate(self.source_columns, start=1)
        ]

    def _context(self, source, target, auto_create=False):
        return SimpleNamespace(
            source_connector=source,
            target_connector=target,
            source_object=SimpleNamespace(
                catalog_name="source_db",
                schema_name="public",
                object_name="items",
            ),
            target_object=SimpleNamespace(
                catalog_name="target_db",
                schema_name="warehouse",
                object_name="items",
            ),
            execution_plan=SimpleNamespace(
                mapping=SimpleNamespace(
                    load_type_code="FULL",
                    load_strategy_code="TRUNCATE_INSERT",
                ),
                load_config=SimpleNamespace(
                    batch_size=100,
                    is_active=True,
                ),
                target_config=SimpleNamespace(
                    auto_create_target=auto_create,
                    target_schema_policy_code=(
                        "CREATE_IF_MISSING"
                        if auto_create
                        else "BLOCK"
                    ),
                ),
            ),
        )

    def test_existing_schema_mismatch_is_reported_without_modification(self):
        source = FakeSchemaConnector(self.source_columns)
        target_columns = [dict(column) for column in self.source_columns]
        target_columns[1]["is_nullable"] = "NO"
        target = FakeSchemaConnector(target_columns)

        results = PreExecutionValidator().validate(
            self._context(source, target),
            self.mapping,
        )

        schema_result = next(
            result
            for result in results
            if result.check_name == "SCHEMA_METADATA_MATCH"
        )
        self.assertFalse(schema_result.passed)
        self.assertIn("is_nullable differs", schema_result.message)
        self.assertIsNone(target.created_columns)
        self.assertEqual(target.commit_count, 0)

    def test_missing_target_is_created_refreshed_and_validated(self):
        source = FakeSchemaConnector(self.source_columns)
        target = FakeSchemaConnector([], exists=False)

        results = PreExecutionValidator().validate(
            self._context(source, target, auto_create=True),
            self.mapping,
        )

        self.assertEqual(target.created_columns, self.source_columns)
        self.assertEqual(target.commit_count, 1)
        self.assertEqual(target.rollback_count, 0)
        self.assertTrue(
            next(
                result
                for result in results
                if result.check_name == "SCHEMA_METADATA_MATCH"
            ).passed
        )

    def test_missing_target_without_create_policy_is_rejected(self):
        source = FakeSchemaConnector(self.source_columns)
        target = FakeSchemaConnector([], exists=False)

        with self.assertRaisesRegex(
            LookupError,
            "does not permit creation",
        ):
            PreExecutionValidator().validate(
                self._context(source, target),
                self.mapping,
            )

        self.assertIsNone(target.created_columns)
        self.assertEqual(target.commit_count, 0)

    def test_mismatched_created_schema_is_rolled_back(self):
        source = FakeSchemaConnector(self.source_columns)
        target = FakeSchemaConnector([], exists=False)
        target.create_mismatched_schema = True

        with self.assertRaisesRegex(
            ValueError,
            "Created target schema does not match",
        ):
            PreExecutionValidator().validate(
                self._context(source, target, auto_create=True),
                self.mapping,
            )

        self.assertFalse(target.exists)
        self.assertEqual(target.rollback_count, 1)
        self.assertEqual(target.commit_count, 0)


if __name__ == "__main__":
    unittest.main()
