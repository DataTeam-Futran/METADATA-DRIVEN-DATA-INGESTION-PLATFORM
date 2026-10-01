"""
PostgreSQL Connector Adapter
============================

PostgreSQL-specific connector implementation for the
Metadata-Driven Data Ingestion Platform.

Responsibilities
----------------
This adapter is responsible for PostgreSQL-specific:

    - Connection management
    - Connection testing
    - Schema discovery
    - Table discovery
    - Column discovery
    - Batch data reading

Credential handling
-------------------
The adapter does not store or hardcode passwords.

The password is resolved at runtime using:

    credential_id
        |
        v
    CredentialResolver
        |
        v
    conn.credential_ref
        |
        v
    SecretProvider
        |
        v
    Runtime secret
        |
        v
    psycopg.connect()
"""

# ---------------------------------------------------------------------
# Future annotations
# ---------------------------------------------------------------------
#
# This allows type annotations to be evaluated more flexibly and keeps
# the module compatible with modern Python typing syntax.

from __future__ import annotations


# ---------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------

# Iterator is used by read_batches() because the method yields batches
# incrementally rather than loading the complete source dataset.
from collections.abc import Iterator

# Any is used for dynamically typed metadata values such as connection
# parameters and database result values.
from typing import Any


# ---------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------

# psycopg is the PostgreSQL driver used by the connector.
import psycopg

# Connection is the psycopg connection type used for type annotations.
from psycopg import Connection

# tuple_row makes psycopg return query rows as tuples, which is the
# structure expected by the current connector implementation.
from psycopg.rows import tuple_row


# ---------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------

# BaseConnector defines the platform-neutral connector contract.
from app.connectors.base import BaseConnector

# CredentialResolver resolves credential_id into the actual runtime
# secret without storing the password in connection metadata.
from app.credentials.resolver import CredentialResolver

# ConnectionMetadata is the platform-neutral connection model.
from app.models.connection import ConnectionMetadata


# ---------------------------------------------------------------------
# PostgreSQL Connector
# ---------------------------------------------------------------------

class PostgreSQLConnector(BaseConnector):
    """
    PostgreSQL implementation of BaseConnector.
    """

    # -----------------------------------------------------------------
    # Constructor
    # -----------------------------------------------------------------

    def __init__(
        self,
        metadata: ConnectionMetadata,
    ) -> None:
        """
        Initialize the PostgreSQL connector.

        The connector stores the platform-neutral metadata and
        initializes its physical PostgreSQL connection as None.

        The actual database connection is created only when connect()
        is called.
        """

        # Initialize the BaseConnector portion of the object.
        super().__init__(metadata)

        # Store the physical PostgreSQL connection internally.

        # Keeping the connection internally allows all connector
        # operations to use the same connection lifecycle.
        self._connection: Connection | None = None

        # Create the credential resolver used to resolve credential_id
        # into the actual password at runtime.
        self._credential_resolver = (
            CredentialResolver()
        )

    # =========================================================
    # INTERNAL PARAMETER HELPERS
    # =========================================================

    def _get_parameter(
        self,
        parameter_name: str,
        required: bool = False,
    ) -> Any:
        """
        Retrieve a dynamic connection parameter.

        Parameters are stored in:

            self.metadata.parameters

        Each parameter is a ConnectionParameter object.
        """

        # Normalize the requested parameter name so metadata lookup
        # remains case-insensitive.
        normalized_name = (
            parameter_name.strip().lower()
        )

        # Read the parameter dictionary from ConnectionMetadata.
        parameters = (
            self.metadata.parameters or {}
        )

        # Start with no matching parameter.
        parameter = None

        # Search the parameter dictionary case-insensitively.
        for name, value in parameters.items():

            if (
                name.strip().lower()
                == normalized_name
            ):
                parameter = value
                break

        # Handle a parameter that does not exist.
        if parameter is None:

            if required:

                raise ValueError(
                    f"Required connection parameter "
                    f"'{parameter_name}' is missing for "
                    f"connection "
                    f"'{self.metadata.connection_name}'."
                )

            return None

        # ConnectionParameter contains the actual parameter value.
        value = parameter.value

        # Handle a parameter whose value is None.
        if value is None:

            if required:

                raise ValueError(
                    f"Required connection parameter "
                    f"'{parameter_name}' is empty for "
                    f"connection "
                    f"'{self.metadata.connection_name}'."
                )

            return None

        # Remove unnecessary whitespace from string values.
        if isinstance(value, str):

            value = value.strip()

            # Treat an empty string as missing.
            if not value:

                if required:

                    raise ValueError(
                        f"Required connection parameter "
                        f"'{parameter_name}' is empty for "
                        f"connection "
                        f"'{self.metadata.connection_name}'."
                    )

                return None

        # Return the resolved parameter value.
        return value

    # =========================================================
    # CONNECTION CONFIGURATION
    # =========================================================

    def _build_connection_kwargs(
        self,
    ) -> dict[str, Any]:
        """
        Build psycopg connection arguments dynamically.

        Physical connection information comes from:

            metadata.host_name
            metadata.port_no
            metadata.database_name

        Username comes from:

            metadata.parameters

        Password comes from:

            metadata.credential_id
                |
                v
            CredentialResolver
        """

        # -----------------------------------------------------
        # HOST
        # -----------------------------------------------------

        # Read the PostgreSQL host from connection metadata.
        host = self.metadata.host_name

        # Host is mandatory for this connector.
        if not host:

            raise ValueError(
                f"Host is missing for connection "
                f"'{self.metadata.connection_name}'."
            )

        # -----------------------------------------------------
        # PORT
        # -----------------------------------------------------

        # Read the PostgreSQL port from connection metadata.
        port = self.metadata.port_no

        # Port is mandatory for this connector.
        if port is None:

            raise ValueError(
                f"Port is missing for connection "
                f"'{self.metadata.connection_name}'."
            )

        # -----------------------------------------------------
        # DATABASE
        # -----------------------------------------------------

        # Read the target/source database name from metadata.
        database = self.metadata.database_name

        # Database name is mandatory for this connector.
        if not database:

            raise ValueError(
                f"Database is missing for connection "
                f"'{self.metadata.connection_name}'."
            )

        # -----------------------------------------------------
        # USERNAME
        # -----------------------------------------------------

        # Username is treated as a dynamic connection parameter.
        username = self._get_parameter(
            "username",
            required=True,
        )

        # -----------------------------------------------------
        # BASE CONNECTION ARGUMENTS
        # -----------------------------------------------------

        # Build the basic psycopg connection arguments.
        kwargs: dict[str, Any] = {
            "host": host,
            "port": port,
            "dbname": database,
            "user": username,
        }

        # -----------------------------------------------------
        # PASSWORD
        # -----------------------------------------------------

        # A credential reference must exist because the adapter does
        # not allow passwords to be stored directly in metadata.
        if self.metadata.credential_id is None:

            raise ValueError(
                f"No credential_id configured for "
                f"connection "
                f"'{self.metadata.connection_name}'."
            )

        # Resolve the actual password at runtime through the
        # credential provider architecture.
        password = (
            self._credential_resolver.resolve(
                self.metadata.credential_id
            )
        )

        # Add the resolved password to the psycopg connection
        # arguments.
        kwargs["password"] = password

        # -----------------------------------------------------
        # SSL MODE
        # -----------------------------------------------------

        # SSL mode is optional and can be supplied through the
        # dynamic connection parameters.
        sslmode = self._get_parameter(
            "sslmode",
            required=False,
        )

        if sslmode is not None:

            kwargs["sslmode"] = str(
                sslmode
            )

        # -----------------------------------------------------
        # APPLICATION NAME
        # -----------------------------------------------------

        # Application name is optional and can be useful for
        # database-side monitoring and troubleshooting.
        application_name = (
            self._get_parameter(
                "application_name",
                required=False,
            )
        )

        if application_name is not None:

            kwargs["application_name"] = str(
                application_name
            )

        # -----------------------------------------------------
        # CONNECTION TIMEOUT
        # -----------------------------------------------------

        # Read the connection timeout from platform metadata.
        connect_timeout = (
            self.metadata.connect_timeout_seconds
        )

        if connect_timeout is not None:

            # The timeout must be positive.
            if connect_timeout <= 0:

                raise ValueError(
                    "connect_timeout_seconds must "
                    "be greater than zero."
                )

            # psycopg expects the timeout in seconds.
            kwargs["connect_timeout"] = (
                connect_timeout
            )

        # Return the complete psycopg connection configuration.
        return kwargs

    # =========================================================
    # CONNECT
    # =========================================================

    def connect(self) -> Connection:
        """
        Establish a PostgreSQL connection and return it.

        The credential is resolved at runtime.

        The connector maintains the connection internally in
        self._connection.

        The same connection object is also returned to the caller so
        runtime services can execute DDL/DML operations using the
        connector-managed connection.
        """

        # -----------------------------------------------------
        # Close existing connection.
        # -----------------------------------------------------

        # Closing an existing connection makes connect() idempotent
        # from the connector's perspective and prevents an old
        # connection from being accidentally reused.
        self.close()

        # -----------------------------------------------------
        # Build dynamic connection arguments.
        # -----------------------------------------------------

        # All physical connection information and credentials are
        # resolved from metadata and the credential provider.
        connection_kwargs = (
            self._build_connection_kwargs()
        )

        try:

            # -------------------------------------------------
            # Create PostgreSQL connection.
            # -------------------------------------------------

            # Create the physical PostgreSQL connection using psycopg.
            #
            # tuple_row ensures query results remain compatible with
            # the existing connector implementation.
            self._connection = (
                psycopg.connect(
                    **connection_kwargs,
                    row_factory=tuple_row,
                )
            )

            # -------------------------------------------------
            # Configure command timeout.
            # -------------------------------------------------

            # Apply PostgreSQL statement_timeout using the platform
            # command timeout metadata.
            self._set_command_timeout()

            # -------------------------------------------------
            # Return active connection.
            # -------------------------------------------------

            # IMPORTANT:
            #
            # The previous implementation established the connection
            # but returned None.
            #
            # Runtime code such as:
            #
            #     target_connection = connector.connect()
            #
            # therefore received None even though
            # self._connection was valid.
            #
            # Returning the same connection object fixes that contract
            # while preserving the connector's internal lifecycle.
            return self._connection

        except Exception:

            # If connection creation or timeout configuration fails,
            # close and clear the partially created connection.
            self.close()

            # Re-raise the original exception so the caller receives
            # the actual connection failure.
            raise

    # =========================================================
    # COMMAND TIMEOUT
    # =========================================================

    def _set_command_timeout(self) -> None:
        """
        Configure PostgreSQL statement_timeout.

        Platform metadata stores the timeout in seconds.

        PostgreSQL statement_timeout uses milliseconds.

        set_config() is used because:

            SET statement_timeout = %s

        does not accept a psycopg bind parameter correctly.
        """

        # If there is no active connection, there is nothing to
        # configure.
        if self._connection is None:

            return

        # Read command timeout from platform metadata.
        timeout_seconds = (
            self.metadata.command_timeout_seconds
        )

        # A None timeout means no platform timeout was configured.
        if timeout_seconds is None:

            return

        # Timeout must be positive.
        if timeout_seconds <= 0:

            raise ValueError(
                "command_timeout_seconds must "
                "be greater than zero."
            )

        # PostgreSQL expects statement_timeout in milliseconds.
        timeout_milliseconds = (
            timeout_seconds * 1000
        )

        # Execute the PostgreSQL configuration command using the
        # active connector-managed connection.
        with self._connection.cursor() as cursor:

            cursor.execute(
                """
                SELECT set_config(
                    'statement_timeout',
                    %s,
                    false
                );
                """,
                (
                    str(timeout_milliseconds),
                ),
            )

    # =========================================================
    # CONNECTION TEST
    # =========================================================

    def test_connection(self) -> bool:
        """
        Test PostgreSQL connectivity using SELECT 1.

        Returns
        -------
        bool
            True when the connection succeeds.
            False when the connection fails.
        """

        try:

            # Establish the PostgreSQL connection.
            self.connect()

            # Defensive validation in case a connector implementation
            # unexpectedly fails to initialize the connection.
            if self._connection is None:

                print(
                    "DEBUG: PostgreSQL connection "
                    "object is None."
                )

                return False

            # Execute a lightweight connectivity query.
            with self._connection.cursor() as cursor:

                cursor.execute(
                    "SELECT 1;"
                )

                row = cursor.fetchone()

            # SELECT 1 should return exactly (1,).
            if row == (1,):

                return True

            # Unexpected result should be treated as a failed test.
            print(
                f"DEBUG: Unexpected SELECT 1 "
                f"result: {row}"
            )

            self.close()

            return False

        except Exception as exc:

            # Development-time diagnostic output.
            #
            # IMPORTANT:
            # Do not print credentials or connection passwords.
            print(
                "\nSOURCE CONNECTION ERROR"
            )

            print(
                f"Error Type : "
                f"{type(exc).__name__}"
            )

            print(
                f"Error      : "
                f"{exc}"
            )

            # Ensure the failed connection is cleaned up.
            self.close()

            return False

    # =========================================================
    # CLOSE CONNECTION
    # =========================================================

    def close(self) -> None:
        """
        Close the PostgreSQL connection safely.
        """

        # Only attempt to close when an active connection exists.
        if self._connection is not None:

            try:

                # Close the psycopg connection.
                self._connection.close()

            except Exception:

                # Connection cleanup should never mask the original
                # exception that caused cleanup to occur.
                pass

            finally:

                # Always clear the internal connection reference.
                self._connection = None

    # =========================================================
    # CONNECTION VALIDATION
    # =========================================================

    def _require_connection(
        self,
    ) -> Connection:
        """
        Return the active PostgreSQL connection.
        """

        # All database operations require an established connection.
        if self._connection is None:

            raise RuntimeError(
                "PostgreSQL connector is not connected. "
                "Call connect() before performing "
                "database operations."
            )

        # Return the active connector-managed connection.
        return self._connection

    # =========================================================
    # SCHEMA DISCOVERY
    # =========================================================

    def list_schemas(self) -> list[str]:
        """
        Return schemas available to the connected user.
        """

        # Resolve the active PostgreSQL connection.
        connection = (
            self._require_connection()
        )

        # information_schema provides a standard metadata interface
        # for PostgreSQL schema discovery.
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name <> 'information_schema'
              AND schema_name NOT LIKE 'pg_%'
            ORDER BY schema_name;
        """

        # Execute the discovery query.
        with connection.cursor() as cursor:

            cursor.execute(query)

            rows = cursor.fetchall()

        # Return only schema names.
        return [
            row[0]
            for row in rows
        ]

    # =========================================================
    # TABLE DISCOVERY
    # =========================================================

    def list_tables(
        self,
        schema_name: str,
    ) -> list[str]:
        """
        Return tables available in a schema.
        """

        # Validate the supplied schema name.
        if (
            not schema_name
            or not schema_name.strip()
        ):

            raise ValueError(
                "schema_name must not be empty."
            )

        # Resolve the active PostgreSQL connection.
        connection = (
            self._require_connection()
        )

        # Query PostgreSQL information_schema for base tables.
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """

        # Execute the table discovery query.
        with connection.cursor() as cursor:

            cursor.execute(
                query,
                (schema_name,),
            )

            rows = cursor.fetchall()

        # Return table names.
        return [
            row[0]
            for row in rows
        ]

    # =========================================================
    # COLUMN DISCOVERY
    # =========================================================

    def list_columns(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        """
        Return column metadata for a PostgreSQL table.

        Returns:

            column_name
            data_type
            ordinal_position
            is_nullable
            column_default
        """

        # Validate schema name.
        if (
            not schema_name
            or not schema_name.strip()
        ):

            raise ValueError(
                "schema_name must not be empty."
            )

        # Validate table name.
        if (
            not table_name
            or not table_name.strip()
        ):

            raise ValueError(
                "table_name must not be empty."
            )

        # Resolve the active PostgreSQL connection.
        connection = (
            self._require_connection()
        )

        # Query column metadata from information_schema.
        query = """
            SELECT
                column_name,
                data_type,
                ordinal_position,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position;
        """

        # Execute the column discovery query.
        with connection.cursor() as cursor:

            cursor.execute(
                query,
                (
                    schema_name,
                    table_name,
                ),
            )

            rows = cursor.fetchall()

        # Convert database rows into the connector's standard
        # column metadata structure.
        return [
            {
                "column_name": row[0],
                "data_type": row[1],
                "ordinal_position": row[2],
                "is_nullable": row[3],
                "column_default": row[4],
            }
            for row in rows
        ]

    # =========================================================
    # BATCH DATA READING
    # =========================================================

    def read_batches(
        self,
        query: str,
        batch_size: int = 1000,
    ) -> Iterator[list[tuple[Any, ...]]]:
        """
        Read source data in controlled batches.

        This method implements the abstract BaseConnector
        read_batches() contract.

        Parameters
        ----------
        query:
            SQL query used to extract source data.

        batch_size:
            Maximum number of rows returned per batch.

        Yields
        ------
        list[tuple[Any, ...]]
            Rows returned in each batch.
        """

        # -----------------------------------------------------
        # Validate query.
        # -----------------------------------------------------

        # Empty SQL cannot be executed safely.
        if not query or not query.strip():

            raise ValueError(
                "query must not be empty."
            )

        # -----------------------------------------------------
        # Validate batch size.
        # -----------------------------------------------------

        # Batch size must be positive to prevent invalid fetch
        # operations.
        if batch_size <= 0:

            raise ValueError(
                "batch_size must be greater than zero."
            )

        # -----------------------------------------------------
        # Get active connection.
        # -----------------------------------------------------

        # Use the connector's internal connection lifecycle.
        connection = (
            self._require_connection()
        )

        # -----------------------------------------------------
        # Generate unique server-side cursor name.
        # -----------------------------------------------------

        # A unique cursor name prevents collisions between multiple
        # connector instances in the same process.
        cursor_name = (
            f"mdip_read_{id(self)}"
        )

        try:

            # -------------------------------------------------
            # PostgreSQL named cursor.
            #
            # This allows large datasets to be processed
            # incrementally rather than loading everything
            # into application memory.
            # -------------------------------------------------

            with connection.cursor(
                name=cursor_name,
            ) as cursor:

                # Execute the source extraction query.
                cursor.execute(query)

                # Continue fetching until the source is exhausted.
                while True:

                    # Fetch only the configured number of rows.
                    rows = cursor.fetchmany(
                        batch_size
                    )

                    # No rows means the source has been completely
                    # consumed.
                    if not rows:

                        break

                    # Yield the current batch to the caller.
                    yield list(rows)

        finally:

            # -------------------------------------------------
            # Clean up the transaction created by the
            # server-side cursor.
            # -------------------------------------------------

            # A named cursor operates inside a transaction when
            # autocommit is disabled.
            if not connection.autocommit:

                # Roll back the read transaction so the connector
                # does not leave an open transaction after extraction.
                connection.rollback()
        # =========================================================
    # BATCH DATA WRITING
    # =========================================================

    def write_batch(
        self,
        target_schema: str,
        target_table: str,
        column_names: list[str],
        rows: list[tuple[Any, ...]],
    ) -> int:
        """
        Write one batch of rows into a PostgreSQL target table.

        IMPORTANT:
        ----------
        This method intentionally does NOT call commit().

        WHY:
        ----
        Transaction control belongs to the runtime execution layer.

        The Full Load Executor will eventually control the complete
        transaction:

            BEGIN
                |
                +-- TRUNCATE
                |
                +-- INSERT batch 1
                |
                +-- INSERT batch 2
                |
                +-- INSERT batch N
                |
              COMMIT

        If execution fails:

            ROLLBACK

        This prevents individual batches from being committed
        independently.
        """

        # -----------------------------------------------------
        # Validate target schema
        # -----------------------------------------------------

        # A schema is required because the target object is resolved
        # from catalog.dataset_binding metadata.
        if not target_schema or not target_schema.strip():
            raise ValueError(
                "target_schema must not be empty."
            )

        # -----------------------------------------------------
        # Validate target table
        # -----------------------------------------------------

        # A target table is required for the INSERT operation.
        if not target_table or not target_table.strip():
            raise ValueError(
                "target_table must not be empty."
            )

        # -----------------------------------------------------
        # Validate column names
        # -----------------------------------------------------

        # At least one target column is required for an INSERT.
        if not column_names:
            raise ValueError(
                "column_names must not be empty."
            )

        # Validate every column name before building the statement.
        for column_name in column_names:
            if not column_name or not column_name.strip():
                raise ValueError(
                    "Target column names must not be empty."
                )

        # -----------------------------------------------------
        # Handle empty batch
        # -----------------------------------------------------

        # An empty batch does not represent an error.
        #
        # Returning zero allows the execution engine to process
        # empty source datasets without performing unnecessary SQL.
        if not rows:
            return 0

        # -----------------------------------------------------
        # Validate row structure
        # -----------------------------------------------------

        # Every row must contain exactly one value for every
        # target column.
        expected_column_count = len(column_names)

        for row in rows:
            if len(row) != expected_column_count:
                raise ValueError(
                    "Row column count does not match "
                    "target column count."
                )

        # -----------------------------------------------------
        # Resolve active PostgreSQL connection
        # -----------------------------------------------------

        # All physical database operations go through the
        # connector-managed connection.
        connection = self._require_connection()

        # -----------------------------------------------------
        # Build INSERT statement
        # -----------------------------------------------------

        # _quote_identifier() safely handles PostgreSQL identifiers
        # such as schema, table, and column names.
        quoted_schema = self._quote_identifier(
            target_schema
        )

        quoted_table = self._quote_identifier(
            target_table
        )

        quoted_columns = ", ".join(
            self._quote_identifier(column_name)
            for column_name in column_names
        )

        # Create one positional placeholder for every target column.
        placeholders = ", ".join(
            ["%s"] * expected_column_count
        )

        # Build the final parameterized INSERT statement.
        #
        # IMPORTANT:
        # Values are passed separately through executemany().
        # They are never concatenated into the SQL string.
        insert_query = (
            f"INSERT INTO "
            f"{quoted_schema}.{quoted_table} "
            f"({quoted_columns}) "
            f"VALUES ({placeholders})"
        )

        # -----------------------------------------------------
        # Execute batch
        # -----------------------------------------------------

        # executemany() sends the complete batch using the same
        # parameterized INSERT statement.
        #
        # We intentionally do NOT call connection.commit().
        # The caller owns the transaction boundary.
        with connection.cursor() as cursor:
            cursor.executemany(
                insert_query,
                rows,
            )

        # -----------------------------------------------------
        # Return batch count
        # -----------------------------------------------------

        # The execution engine uses this value for runtime metrics,
        # reconciliation, and logging.
        return len(rows)

        # =========================================================
    # TRANSACTION MANAGEMENT
    # =========================================================

    def begin_transaction(self) -> None:
        """
        Begin a PostgreSQL transaction.

        WHY:
        ----
        psycopg starts transactions automatically when SQL is
        executed, but the ingestion platform exposes an explicit
        transaction method so the runtime engine has a common
        contract across database technologies.

        For PostgreSQL, this method validates that the connector
        has an active connection.

        The actual transaction begins when the first SQL statement
        is executed.
        """

        # Make sure a physical PostgreSQL connection exists.
        self._require_connection()

    def commit(self) -> None:
        """
        Commit the current PostgreSQL transaction.

        WHY:
        ----
        The Full Load Executor owns the transaction boundary.

        Therefore commit() is called only after all batches have
        been successfully written.
        """

        # Resolve the active connector-managed connection.
        connection = self._require_connection()

        # Commit all changes made during the current transaction.
        connection.commit()

    def rollback(self) -> None:
        """
        Roll back the current PostgreSQL transaction.

        WHY:
        ----
        If the full-load execution fails, the runtime engine can
        remove all uncommitted target changes.
        """

        # Resolve the active connector-managed connection.
        connection = self._require_connection()

        # Roll back all uncommitted changes.
        connection.rollback()

    # =========================================================
    # TARGET TABLE PREPARATION
    # =========================================================

    def truncate_table(
        self,
        target_schema: str,
        target_table: str,
    ) -> None:
        """
        Truncate a PostgreSQL target table.

        IMPORTANT:
        ----------
        This method does NOT commit.

        WHY:
        ----
        TRUNCATE must participate in the same target transaction
        as the subsequent INSERT batches.

        This allows the execution engine to perform:

            BEGIN
                |
                +-- TRUNCATE
                |
                +-- INSERT batch 1
                |
                +-- INSERT batch 2
                |
                +-- ...
                |
              COMMIT

        If loading fails, the transaction can be rolled back.
        """

        # Validate target schema.
        if not target_schema or not target_schema.strip():
            raise ValueError(
                "target_schema must not be empty."
            )

        # Validate target table.
        if not target_table or not target_table.strip():
            raise ValueError(
                "target_table must not be empty."
            )

        # Resolve the active PostgreSQL connection.
        connection = self._require_connection()

        # Safely quote the schema and table identifiers.
        quoted_schema = self._quote_identifier(
            target_schema
        )

        quoted_table = self._quote_identifier(
            target_table
        )

        # Build the PostgreSQL TRUNCATE statement.
        truncate_query = (
            f"TRUNCATE TABLE "
            f"{quoted_schema}.{quoted_table}"
        )

        # Execute TRUNCATE without committing.
        with connection.cursor() as cursor:
            cursor.execute(truncate_query)

    # =========================================================
    # IDENTIFIER HANDLING
    # =========================================================

    @staticmethod
    def _quote_identifier(
        identifier: str,
    ) -> str:
        """
        Safely quote a PostgreSQL identifier.
        """

        # Validate the identifier.
        if (
            not identifier
            or not identifier.strip()
        ):

            raise ValueError(
                "PostgreSQL identifier must "
                "not be empty."
            )

        # Remove surrounding whitespace.
        identifier = identifier.strip()

        # Escape embedded double quotes according to PostgreSQL
        # identifier rules.
        escaped_identifier = (
            identifier.replace(
                '"',
                '""',
            )
        )

        # Return the safely quoted PostgreSQL identifier.
        return (
            f'"{escaped_identifier}"'
        )