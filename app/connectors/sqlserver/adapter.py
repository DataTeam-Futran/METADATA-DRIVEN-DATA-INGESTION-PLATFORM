
"""
SQL Server Connector
====================

Purpose
-------
Implements the platform's common BaseConnector contract for Microsoft
SQL Server using pyodbc and a Microsoft ODBC driver.

Responsibilities
----------------
1. Resolve SQL Server connection details from metadata.
2. Resolve the password through CredentialResolver.
3. Connect to SQL Server.
4. Discover schemas, tables, and columns.
5. Read data in batches.
6. Insert data in batches.
7. Manage target transactions.
8. Truncate target tables when requested.

Architecture
------------
PostgreSQL Source
        |
        v
PostgreSQLConnector.read_batches()
        |
        v
Generic Full Load Executor
        |
        v
SQLServerConnector.write_batch()
        |
        v
SQL Server Target

Important
---------
- No credentials are hardcoded.
- SQL values use parameterized queries.
- Identifiers are safely quoted using SQL Server brackets.
- Batch writes do not commit automatically.
- The executor controls commit and rollback.
"""

# Iterator describes the batches returned by read_batches().
from collections.abc import Iterator
from typing import Any

# pyodbc provides connectivity through the installed Windows ODBC driver.
import pyodbc

# Import the shared connector contract.
from app.connectors.base import BaseConnector

# Import the existing credential-resolution service.
from app.credentials.resolver import CredentialResolver

# Use the existing connection metadata model.
from app.models.connection import ConnectionMetadata


class SQLServerConnector(BaseConnector):
    """
    SQL Server implementation of the common connector contract.

    The connector receives resolved connection metadata, but it does not
    open a physical connection until connect() is called.
    """

    def __init__(self, metadata: ConnectionMetadata) -> None:
        """Initialize the connector without opening a database connection."""

        # Store connection metadata using the common base implementation.
        super().__init__(metadata)

        # Hold the physical SQL Server connection after connect() succeeds.
        self._connection: pyodbc.Connection | None = None

        # Reuse the platform's existing credential-resolution mechanism.
        self._credential_resolver = CredentialResolver()

    # ------------------------------------------------------------------
    # METADATA PARAMETER HELPERS
    # ------------------------------------------------------------------

    def _get_parameter(self, name: str) -> str | None:
        """
        Retrieve an optional connector parameter from connection metadata.

        WHY:
        Connector-specific settings should come from metadata rather than
        being hardcoded throughout the implementation.
        """

        # Normalize the requested name for case-insensitive matching.
        normalized_name = name.strip().lower()

        # Inspect the parameters already resolved for this connection.
        for parameter_name, parameter in self.metadata.parameters.items():
            if parameter_name.strip().lower() == normalized_name:
                # Return the configured value as text when it is present.
                if parameter.value is None:
                    return None

                return str(parameter.value)

        # No value was configured for this parameter.
        return None

    @staticmethod
    def _odbc_value(value: str) -> str:
        """
        Escape a value for use in an ODBC connection string.

        WHY:
        Connection-string values may contain semicolons or closing braces.
        Bracing and escaping prevent those characters from being interpreted
        as additional connection-string properties.
        """

        # Escape a closing brace according to ODBC connection-string rules.
        escaped_value = value.replace("}", "}}")

        # Enclose the complete value in braces.
        return "{" + escaped_value + "}"

    def _build_connection_string(self) -> str:
        """
        Build the SQL Server ODBC connection string from metadata.

        Required metadata:
            host_name
            database_name
            username parameter
            credential_id

        Optional parameters:
            odbc_driver
            encrypt
            trust_server_certificate
        """

        # Obtain the server host from the resolved connection metadata.
        host_name = self.metadata.host_name

        # Obtain the target database name from connection metadata.
        database_name = self.metadata.database_name

        # Username is stored as a connection parameter in this platform.
        username = self._get_parameter("username")

        # Validate required non-secret connection details.
        if not host_name:
            raise ValueError(
                "SQL Server connection metadata is missing host_name."
            )

        if not database_name:
            raise ValueError(
                "SQL Server connection metadata is missing database_name."
            )

        if not username:
            raise ValueError(
                "SQL Server connection metadata is missing the username "
                "parameter."
            )

        # A credential reference is required to resolve the password.
        if self.metadata.credential_id is None:
            raise ValueError(
                "SQL Server connection metadata is missing credential_id."
            )

        # Resolve the password without printing or storing it in metadata.
        password = self._credential_resolver.resolve(
            self.metadata.credential_id
        )

        # Use the configured port, or SQL Server's conventional port.
        port_no = self.metadata.port_no or 1433

        # Allow the ODBC driver to be overridden through connection metadata.
        driver = (
            self._get_parameter("odbc_driver")
            or "ODBC Driver 18 for SQL Server"
        )

        # Encrypt connections by default.
        #
        # ODBC Driver 18 enables encryption by default as well, but we set
        # it explicitly so that the intended security behavior is visible.
        encrypt = (
            self._get_parameter("encrypt") or "yes"
        ).strip().lower()

        # Certificate validation is enabled by default.
        #
        # For production, use a certificate trusted by the client machine.
        # Do not disable certificate validation merely to hide a TLS error.
        trust_server_certificate = (
            self._get_parameter("trust_server_certificate") or "no"
        ).strip().lower()

        # Accept only explicit Boolean-style ODBC settings.
        if encrypt not in {"yes", "no"}:
            raise ValueError(
                "SQL Server parameter 'encrypt' must be 'yes' or 'no'."
            )

        if trust_server_certificate not in {"yes", "no"}:
            raise ValueError(
                "SQL Server parameter 'trust_server_certificate' "
                "must be 'yes' or 'no'."
            )

        # Construct the network address without hardcoding a server.
        server_address = f"tcp:{host_name},{port_no}"

        # Assemble the ODBC connection string.
        #
        # Bracing values prevents semicolons and other special characters
        # in credentials or names from changing connection-string parsing.
        connection_string = (
            f"DRIVER={self._odbc_value(driver)};"
            f"SERVER={self._odbc_value(server_address)};"
            f"DATABASE={self._odbc_value(database_name)};"
            f"UID={self._odbc_value(username)};"
            f"PWD={self._odbc_value(password)};"
            f"Encrypt={encrypt};"
            f"TrustServerCertificate={trust_server_certificate};"
            f"Connection Timeout={self.metadata.connect_timeout_seconds};"
        )

        # Return the connection string to the connection method.
        # Never print it because it contains the password.
        return connection_string

    # ------------------------------------------------------------------
    # CONNECTION MANAGEMENT
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """
        Open a physical connection to SQL Server.

        Repeated calls reuse an existing connection.
        """

        # Avoid opening a second connection when one is already available.
        if self._connection is not None:
            if self._connection.closed:
                self._connection = None
            else:
                return

        # Build the connection string using metadata and resolved credentials.
        connection_string = self._build_connection_string()

        # Open the connection with autocommit disabled.
        #
        # WHY:
        # Target writes must remain under explicit transaction control so
        # the executor can commit a successful load or roll it back on error.
        self._connection = pyodbc.connect(
            connection_string,
            autocommit=False,
            timeout=self.metadata.connect_timeout_seconds,
        )

    def test_connection(self) -> bool:
        """
        Test whether SQL Server can execute a simple query.

        Returns True when successful and False when connection testing fails.
        """

        # Remember whether this method opened the connection itself.
        opened_here = self._connection is None

        try:
            # Open the connection if the caller has not already done so.
            self.connect()

            # Execute a lightweight query to validate connectivity.
            with self._require_connection().cursor() as cursor:
                self._require_connection().timeout = self.metadata.command_timeout_seconds
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()

            # A valid result confirms that the connection is usable.
            return row is not None and row[0] == 1

        except pyodbc.Error:
            # Return failure without exposing credentials or connection text.
            return False

        finally:
            # Close only a connection created by this test operation.
            #
            # Do not unexpectedly close a connection owned by the executor.
            if opened_here:
                self.close()

    def close(self) -> None:
        """Close the physical SQL Server connection and release resources."""

        # Close only when a connection exists.
        if self._connection is not None:
            try:
                self._connection.close()
            finally:
                # Clear the reference even if closing raises an error.
                self._connection = None

    def _require_connection(self) -> pyodbc.Connection:
        """
        Return the active connection or raise a clear lifecycle error.

        WHY:
        Database operations must not run before connect() has succeeded.
        """

        # Reject operations when no connection has been opened.
        if self._connection is None:
            raise RuntimeError(
                "SQL Server connection is not open. Call connect() first."
            )

        # Reject operations after the connection has been closed.
        if self._connection.closed:
            raise RuntimeError(
                "SQL Server connection is closed. Call connect() again."
            )

        # Return the active physical connection.
        return self._connection

    # ------------------------------------------------------------------
    # SCHEMA AND TABLE DISCOVERY
    # ------------------------------------------------------------------

    def list_schemas(self) -> list[str]:
        """Return user-visible schemas available in the connected database."""

        # Define a SQL Server catalog query that excludes system schemas.
        query = """
            SELECT name
            FROM sys.schemas
            WHERE name NOT IN ('sys', 'INFORMATION_SCHEMA')
            ORDER BY name;
        """

        # Execute discovery using the active SQL Server connection.
        with self._require_connection().cursor() as cursor:
            self._require_connection().timeout = self.metadata.command_timeout_seconds
            cursor.execute(query)

            # Return the schema names as a simple Python list.
            return [row[0] for row in cursor.fetchall()]

    def list_tables(self, schema_name: str) -> list[str]:
        """Return base tables in the requested SQL Server schema."""

        # Validate the schema name before querying the catalog.
        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")

        # Parameterize the schema filter to avoid SQL injection.
        query = """
            SELECT TABLE_NAME
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = ?
              AND TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME;
        """

        # Execute discovery with a bound schema-name parameter.
        with self._require_connection().cursor() as cursor:
            self._require_connection().timeout = self.metadata.command_timeout_seconds
            cursor.execute(query, schema_name)

            # Return table names only.
            return [row[0] for row in cursor.fetchall()]

    def list_columns(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        """
        Return column metadata for one SQL Server table.

        This helper is useful for schema validation and future discovery work.
        It is not an additional abstract method in BaseConnector.
        """

        # Validate identifiers supplied to the discovery operation.
        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")

        if not table_name or not table_name.strip():
            raise ValueError("table_name must not be empty.")

        # Query SQL Server's information schema using parameters.
        query = """
            SELECT
                COLUMN_NAME,
                DATA_TYPE,
                IS_NULLABLE,
                ORDINAL_POSITION,
                COLUMN_DEFAULT,
                CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION,
                NUMERIC_SCALE,
                DATETIME_PRECISION
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = ?
              AND TABLE_NAME = ?
            ORDER BY ORDINAL_POSITION;
        """

        # Fetch column metadata without constructing SQL from user values.
        with self._require_connection().cursor() as cursor:
            self._require_connection().timeout = self.metadata.command_timeout_seconds
            cursor.execute(query, schema_name, table_name)

            # Convert each row into a readable dictionary.
            return [
                {
                    "column_name": row[0],
                    "data_type": row[1],
                    "is_nullable": row[2] == "YES",
                    "ordinal_no": row[3],
                    "column_default": row[4],
                    "character_maximum_length": row[5],
                    "numeric_precision": row[6],
                    "numeric_scale": row[7],
                    "datetime_precision": row[8],
                }
                for row in cursor.fetchall()
            ]

    # ------------------------------------------------------------------
    # BATCH DATA READING
    # ------------------------------------------------------------------

    def read_batches(
        self,
        query: str,
        batch_size: int,
    ) -> Iterator[list[tuple[Any, ...]]]:
        """
        Read query results in bounded batches.

        Parameters
        ----------
        query:
            SQL query to execute against SQL Server.
        batch_size:
            Maximum number of rows returned in each batch.
        """

        # Validate the batch size to prevent invalid fetch operations.
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        # Validate that the supplied query is not empty.
        if not query or not query.strip():
            raise ValueError("query must not be empty.")

        # Create a cursor for the source extraction query.
        with self._require_connection().cursor() as cursor:
            # Apply the configured query timeout.
            self._require_connection().timeout = self.metadata.command_timeout_seconds

            # Execute the supplied query.
            cursor.execute(query)

            # Fetch only a limited number of rows at a time.
            while True:
                rows = cursor.fetchmany(batch_size)

                # Stop when SQL Server returns no additional rows.
                if not rows:
                    break

                # Yield immutable tuples in a list for the executor.
                yield [tuple(row) for row in rows]

    # ------------------------------------------------------------------
    # SAFE IDENTIFIER QUOTING
    # ------------------------------------------------------------------

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Quote a SQL Server identifier using square brackets.

        WHY:
        Identifiers cannot be passed as ordinary SQL parameters.
        Correct quoting protects identifiers containing reserved words or
        closing brackets. It is not a substitute for metadata validation.
        """

        # Reject missing or blank identifiers.
        if not identifier or not identifier.strip():
            raise ValueError("SQL Server identifier must not be empty.")

        # Escape a closing bracket by doubling it.
        escaped_identifier = identifier.replace("]", "]]")

        # Return the identifier in SQL Server's bracket-quoted form.
        return f"[{escaped_identifier}]"

    # ------------------------------------------------------------------
    # BATCH DATA WRITING
    # ------------------------------------------------------------------

    def write_batch(
        self,
        target_schema: str,
        target_table: str,
        column_names: list[str],
        rows: list[tuple[Any, ...]],
    ) -> int:
        """
        Insert one batch of rows into a SQL Server target table.

        This method deliberately does not commit the transaction.
        """

        # Validate target object names.
        if not target_schema or not target_schema.strip():
            raise ValueError("target_schema must not be empty.")

        if not target_table or not target_table.strip():
            raise ValueError("target_table must not be empty.")

        # Require an explicit ordered column list for every insert.
        if not column_names:
            raise ValueError("column_names must not be empty.")

        # Avoid executing unnecessary SQL for an empty batch.
        if not rows:
            return 0

        # Reject blank column names before building the insert statement.
        if any(not name or not name.strip() for name in column_names):
            raise ValueError("column_names must not contain blank values.")

        # Confirm that each row matches the expected target column count.
        expected_width = len(column_names)

        if any(len(row) != expected_width for row in rows):
            raise ValueError(
                "Each row must contain exactly "
                f"{expected_width} values."
            )

        # Quote each target identifier using SQL Server syntax.
        quoted_schema = self._quote_identifier(target_schema)
        quoted_table = self._quote_identifier(target_table)

        quoted_columns = ", ".join(
            self._quote_identifier(column_name)
            for column_name in column_names
        )

        # Create one parameter placeholder per target column.
        #
        # pyodbc uses question-mark placeholders rather than psycopg's %s.
        placeholders = ", ".join("?" for _ in column_names)

        # Construct the insert statement using only quoted identifiers.
        #
        # Actual data values are passed separately through executemany().
        insert_sql = (
            f"INSERT INTO {quoted_schema}.{quoted_table} "
            f"({quoted_columns}) "
            f"VALUES ({placeholders});"
        )

        # Execute the batch on the existing target transaction.
        with self._require_connection().cursor() as cursor:
            self._require_connection().timeout = self.metadata.command_timeout_seconds

            # Enable the driver's optimized batch path where supported.
            cursor.fast_executemany = True

            # Send the rows as parameterized values.
            cursor.executemany(insert_sql, rows)

        # Report the number of input rows submitted successfully.
        #
        # The executor must commit before treating the load as durable.
        return len(rows)

    # ------------------------------------------------------------------
    # TRANSACTION MANAGEMENT
    # ------------------------------------------------------------------

    def begin_transaction(self) -> None:
        """
        Validate that a target connection is available for a transaction.

        With autocommit disabled, pyodbc manages the transaction around
        subsequent SQL statements. This method does not issue BEGIN TRANSACTION
        because driver behavior and SQL Server transaction state must remain
        consistent.
        """

        # Fail immediately if the target connection is unavailable.
        self._require_connection()

    def commit(self) -> None:
        """Commit all pending SQL Server changes on the active connection."""

        # Commit only through the connector's physical connection.
        self._require_connection().commit()

    def rollback(self) -> None:
        """Roll back pending SQL Server changes on the active connection."""

        # Roll back only through the connector's physical connection.
        self._require_connection().rollback()

    # ------------------------------------------------------------------
    # TARGET TABLE PREPARATION
    # ------------------------------------------------------------------
    
    
    def schema_exists(self, schema_name: str) -> bool:
        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")

        query = """
            SELECT CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM sys.schemas
                    WHERE name = ?
                )
                THEN 1 ELSE 0
            END;
        """

        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds

        with connection.cursor() as cursor:
            cursor.execute(query, schema_name.strip())
            row = cursor.fetchone()

        return bool(row[0])

    def table_exists(
        self,
        schema_name: str,
        table_name: str,
    ) -> bool:
        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")
        if not table_name or not table_name.strip():
            raise ValueError("table_name must not be empty.")

        query = """
            SELECT CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM sys.tables AS t
                    INNER JOIN sys.schemas AS s
                        ON s.schema_id = t.schema_id
                    WHERE s.name = ?
                      AND t.name = ?
                )
                THEN 1 ELSE 0
            END;
        """

        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds

        with connection.cursor() as cursor:
            cursor.execute(
                query,
                schema_name.strip(),
                table_name.strip(),
            )
            row = cursor.fetchone()

        return bool(row[0])

    def create_schema(self, schema_name: str) -> None:
        quoted_schema = self._quote_identifier(schema_name)

        # Schema names are identifiers, so they cannot be passed as
        # ordinary SQL parameters in a CREATE SCHEMA statement.
        query = (
            f"IF SCHEMA_ID(N'{schema_name.strip().replace(chr(39), chr(39) * 2)}') "
            f"IS NULL EXEC(N'CREATE SCHEMA {quoted_schema}');"
        )

        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds

        with connection.cursor() as cursor:
            cursor.execute(query)

    @staticmethod
    def _target_column_type(
        data_type: str,
        column_metadata: dict[str, Any] | None = None,
    ) -> str:
        """Map supported source types to safe SQL Server types."""
        normalized = data_type.strip().lower()
        metadata = column_metadata or {}

        def sized_type(
            type_name: str,
            *,
            maximum_length: int,
        ) -> str:
            length = metadata.get("character_maximum_length")
            if length == -1:
                return f"{type_name}(MAX)"
            if isinstance(length, int) and length > 0:
                if length > maximum_length:
                    raise ValueError(
                        f"{type_name} length {length} exceeds "
                        f"SQL Server's limit of {maximum_length}."
                    )
                return f"{type_name}({length})"
            raise ValueError(
                f"Missing valid character_maximum_length for "
                f"{normalized!r}."
            )

        type_map = {
            "text": "NVARCHAR(MAX)",
            "ntext": "NVARCHAR(MAX)",
            "varchar": "VARCHAR(MAX)",
            "nvarchar": "NVARCHAR(MAX)",
            "character varying": "NVARCHAR(MAX)",
            "character": "NCHAR(1)",
            "char": "CHAR(1)",
            "nchar": "NCHAR(1)",
            "integer": "INT",
            "int": "INT",
            "int2": "SMALLINT",
            "smallint": "SMALLINT",
            "int4": "INT",
            "int8": "BIGINT",
            "bigint": "BIGINT",
            "numeric": "DECIMAL(38, 10)",
            "decimal": "DECIMAL(38, 10)",
            "real": "REAL",
            "double precision": "FLOAT",
            "float": "FLOAT",
            "boolean": "BIT",
            "bool": "BIT",
            "date": "DATE",
            "datetime": "DATETIME",
            "smalldatetime": "SMALLDATETIME",
            "datetime2": "DATETIME2",
            "datetimeoffset": "DATETIMEOFFSET",
            "timestamp without time zone": "DATETIME2",
            "timestamp with time zone": "DATETIMEOFFSET",
            "time": "TIME",
            "time without time zone": "TIME",
            "time with time zone": "TIME",
            "binary": "VARBINARY(MAX)",
            "varbinary": "VARBINARY(MAX)",
            "image": "VARBINARY(MAX)",
            "bytea": "VARBINARY(MAX)",
            "uuid": "UNIQUEIDENTIFIER",
            "uniqueidentifier": "UNIQUEIDENTIFIER",
        }

        if normalized in {"varchar", "nvarchar", "char", "nchar"}:
            type_limits = {
                "varchar": 8000,
                "nvarchar": 4000,
                "char": 8000,
                "nchar": 4000,
            }
            return sized_type(
                normalized.upper(),
                maximum_length=type_limits[normalized],
            )

        if normalized in {"decimal", "numeric"}:
            precision = metadata.get("numeric_precision")
            scale = metadata.get("numeric_scale")
            if isinstance(precision, int) and 1 <= precision <= 38:
                if not isinstance(scale, int) or not 0 <= scale <= precision:
                    raise ValueError(
                        "Unsupported SQL Server precision/scale metadata: "
                        f"precision={precision}, scale={scale}."
                    )
                return f"DECIMAL({precision}, {scale})"

        if normalized in {
            "datetime2",
            "datetimeoffset",
            "time",
            "time without time zone",
            "time with time zone",
            "timestamp without time zone",
            "timestamp with time zone",
        }:
            precision = metadata.get("datetime_precision")
            if isinstance(precision, int):
                if not 0 <= precision <= 7:
                    raise ValueError(
                        "SQL Server temporal precision must be between 0 "
                        "and 7."
                    )
                return f"{type_map[normalized]}({precision})"

        if normalized not in type_map:
            raise ValueError(
                f"Unsupported source data type for SQL Server target: "
                f"{data_type!r}"
            )

        return type_map[normalized]

    def create_table(
        self,
        schema_name: str,
        table_name: str,
        columns: list[dict[str, Any]],
    ) -> None:
        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")
        if not table_name or not table_name.strip():
            raise ValueError("table_name must not be empty.")
        if not columns:
            raise ValueError("columns must contain at least one column.")

        if not self.schema_exists(schema_name):
            raise LookupError(
                f"Target schema does not exist: {schema_name}"
            )

        if self.table_exists(schema_name, table_name):
            return

        ordered_columns = sorted(
            columns,
            key=lambda col: col.get(
                "ordinal_position",
                col.get("ordinal_no", 0),
            ),
        )

        definitions = []

        for column in ordered_columns:
            column_name = column.get("column_name")
            data_type = column.get("data_type")

            if not isinstance(column_name, str) or not column_name.strip():
                raise ValueError("Every column needs a valid column_name.")
            if not isinstance(data_type, str) or not data_type.strip():
                raise ValueError(
                    f"Missing data_type for column {column_name!r}."
                )

            quoted_column = self._quote_identifier(column_name)
            target_type = self._target_column_type(data_type, column)

            nullable = column.get("is_nullable", True)
            if isinstance(nullable, str):
                nullable = nullable.strip().upper() in ("YES", "TRUE", "Y")

            null_clause = "" if nullable else " NOT NULL"

            definitions.append(
                f"{quoted_column} {target_type}{null_clause}"
            )

        quoted_table = (
            f"{self._quote_identifier(schema_name)}."
            f"{self._quote_identifier(table_name)}"
        )

        query = (
            f"CREATE TABLE {quoted_table} "
            f"({', '.join(definitions)});"
        )

        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds

        with connection.cursor() as cursor:
            cursor.execute(query)

    def add_column(
        self,
        schema_name: str,
        table_name: str,
        column: dict[str, Any],
    ) -> None:
        column_name = column.get("column_name")
        data_type = column.get("data_type")
        if not isinstance(column_name, str) or not column_name.strip():
            raise ValueError("Every column needs a valid column_name.")
        if not isinstance(data_type, str) or not data_type.strip():
            raise ValueError(
                f"Missing data_type for column {column_name!r}."
            )

        nullable = column.get("is_nullable", True)
        if isinstance(nullable, str):
            nullable = nullable.strip().upper() in ("YES", "TRUE", "Y")

        quoted_table = (
            f"{self._quote_identifier(schema_name)}."
            f"{self._quote_identifier(table_name)}"
        )
        query = (
            f"ALTER TABLE {quoted_table} ADD "
            f"{self._quote_identifier(column_name)} "
            f"{self._target_column_type(data_type, column)}"
            f"{'' if nullable else ' NOT NULL'};"
        )
        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds
        with connection.cursor() as cursor:
            cursor.execute(query)

    def drop_column(
        self,
        schema_name: str,
        table_name: str,
        column_name: str,
    ) -> None:
        if not column_name or not column_name.strip():
            raise ValueError("column_name must not be empty.")
        quoted_table = (
            f"{self._quote_identifier(schema_name)}."
            f"{self._quote_identifier(table_name)}"
        )
        query = (
            f"ALTER TABLE {quoted_table} DROP COLUMN "
            f"{self._quote_identifier(column_name)};"
        )
        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds
        with connection.cursor() as cursor:
            cursor.execute(query)

    def count_rows(
        self,
        schema_name: str,
        table_name: str,
    ) -> int:
        """Return the row count for a SQL Server table."""

        if not schema_name or not schema_name.strip():
            raise ValueError("schema_name must not be empty.")

        if not table_name or not table_name.strip():
            raise ValueError("table_name must not be empty.")

        qualified_table = (
            f"{self._quote_identifier(schema_name)}."
            f"{self._quote_identifier(table_name)}"
        )

        query = f"SELECT COUNT_BIG(*) FROM {qualified_table};"

        connection = self._require_connection()
        connection.timeout = self.metadata.command_timeout_seconds

        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Row count query returned no result for "
                f"{schema_name}.{table_name}."
            )

        return int(row[0])


    def truncate_table(
        self,
        target_schema: str,
        target_table: str,
    ) -> None:
        """
        Remove all rows from the specified SQL Server table.

        The caller is responsible for committing or rolling back the
        transaction after target preparation and batch insertion.
        """

        # Validate the target object names.
        if not target_schema or not target_schema.strip():
            raise ValueError("target_schema must not be empty.")

        if not target_table or not target_table.strip():
            raise ValueError("target_table must not be empty.")

        # Quote schema and table separately to prevent identifier injection.
        quoted_schema = self._quote_identifier(target_schema)
        quoted_table = self._quote_identifier(target_table)

        # SQL Server supports TRUNCATE TABLE, subject to database restrictions.
        truncate_sql = (
            f"TRUNCATE TABLE {quoted_schema}.{quoted_table};"
        )

        # Execute the truncate without committing it automatically.
        with self._require_connection().cursor() as cursor:
            self._require_connection().timeout = self.metadata.command_timeout_seconds
            cursor.execute(truncate_sql)
