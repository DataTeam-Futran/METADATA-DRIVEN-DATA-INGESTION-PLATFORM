"""
Full Load Executor
==================

Purpose
-------
Executes a metadata-driven FULL LOAD from a source physical object
to a target physical object.

Current supported execution pattern
-----------------------------------
    FULL
      +
    TRUNCATE_INSERT
      +
    DIRECT field mappings

Execution flow
--------------
    RuntimeExecutionContext
            +
    RuntimeFieldMapping[]
            |
            v
    FullLoadExecutor
            |
            +--> Connect source
            |
            +--> Connect target
            |
            +--> Begin target transaction
            |
            +--> Truncate target
            |
            +--> Read source in batches
            |
            +--> Write each batch to target
            |
            +--> Commit target transaction
            |
            +--> Close connections

Failure flow
------------
    Any execution error
            |
            v
       Target rollback
            |
            v
       Close connections
            |
            v
       Re-raise error

Important
---------
This executor does NOT query metadata tables directly.

All metadata required for execution must already be resolved into:

    RuntimeExecutionContext
    RuntimeFieldMapping

This keeps metadata resolution separate from physical data movement.
"""

# Any is used for generic row values returned by database connectors.
from typing import Any

# BaseConnector provides the vendor-neutral connector contract.
from app.connectors.base import BaseConnector

# Runtime execution context contains the resolved source/target objects
# and their corresponding connectors.
from app.runtime.execution_context import RuntimeExecutionContext

# RuntimeFieldMapping contains the resolved source-to-target field mapping.
from app.runtime.models import RuntimeFieldMapping


class FullLoadExecutor:
    """
    Executes one metadata-driven full-load operation.

    The executor is intentionally database-agnostic.

    It interacts only with BaseConnector methods, so the same execution
    logic can eventually work with:

        PostgreSQL
        MySQL
        SQL Server
        Oracle
        Snowflake
        Databricks
        etc.

    Database-specific behavior remains inside the connector layer.
    """

    def execute(
        self,
        context: RuntimeExecutionContext,
        field_mappings: list[RuntimeFieldMapping],
    ) -> int:
        """
        Execute the full source-to-target load.

        Parameters
        ----------
        context:
            Complete runtime execution context containing:

                - execution plan
                - source object
                - target object
                - source connector
                - target connector

        field_mappings:
            Resolved source-to-target field mappings.

        Returns
        -------
        int
            Total number of rows written to the target.

        Raises
        ------
        ValueError
            When the execution configuration is invalid.

        RuntimeError
            When runtime execution fails.

        Important
        ---------
        The target transaction is controlled entirely by this method.

        Therefore:

            BEGIN
            TRUNCATE
            INSERT batches
            COMMIT

        or, on failure:

            BEGIN
            TRUNCATE
            INSERT batches
            ROLLBACK
        """

        # ---------------------------------------------------------
        # VALIDATE EXECUTION INPUT
        # ---------------------------------------------------------

        # A runtime context is mandatory because it contains all
        # physical source/target information required for execution.
        if context is None:
            raise ValueError(
                "Runtime execution context must not be None."
            )

        # At least one source-to-target field mapping is required.
        if not field_mappings:
            raise ValueError(
                "At least one field mapping is required "
                "for full-load execution."
            )

        # ---------------------------------------------------------
        # READ EXECUTION CONFIGURATION
        # ---------------------------------------------------------

        # The execution plan was already resolved from metadata.
        execution_plan = context.execution_plan

        # Mapping configuration defines the logical load type and
        # physical load strategy.
        mapping = execution_plan.mapping

        # Generic load configuration contains the batch size and
        # truncate behavior.
        load_config = execution_plan.load_config

        # Target configuration controls target-side execution behavior.
        target_config = execution_plan.target_config

        # ---------------------------------------------------------
        # VALIDATE CURRENT FULL-LOAD POC
        # ---------------------------------------------------------

        # The first runtime implementation intentionally supports
        # only FULL load.
        if mapping.load_type_code.upper() != "FULL":
            raise ValueError(
                "FullLoadExecutor supports only FULL load. "
                f"Received load_type_code="
                f"'{mapping.load_type_code}'."
            )

        # The current implementation supports the TRUNCATE_INSERT
        # strategy only.
        if mapping.load_strategy_code.upper() != "TRUNCATE_INSERT":
            raise ValueError(
                "FullLoadExecutor supports only "
                "TRUNCATE_INSERT strategy. "
                f"Received load_strategy_code="
                f"'{mapping.load_strategy_code}'."
            )

        # A positive batch size is required for controlled source
        # extraction.
        if load_config.batch_size <= 0:
            raise ValueError(
                "Load configuration batch_size must be "
                "greater than zero."
            )

        # The current strategy requires target truncation.
        if not load_config.truncate_before_load:
            raise ValueError(
                "TRUNCATE_INSERT requires "
                "truncate_before_load=True."
            )

        # ---------------------------------------------------------
        # RESOLVE SOURCE/TARGET OBJECT INFORMATION
        # ---------------------------------------------------------

        # Source physical object was already resolved by the
        # RuntimeObjectResolver.
        source_object = context.source_object

        # Target physical object was already resolved by the
        # RuntimeObjectResolver.
        target_object = context.target_object

        # Source connector is responsible for reading source data.
        source_connector = context.source_connector

        # Target connector is responsible for preparing and writing
        # target data.
        target_connector = context.target_connector

        # ---------------------------------------------------------
        # VALIDATE PHYSICAL OBJECT INFORMATION
        # ---------------------------------------------------------

        # A source schema is required for the generated SELECT.
        if not source_object.schema_name:
            raise ValueError(
                "Source schema is required for full-load execution."
            )

        # A source object name is required for the generated SELECT.
        if not source_object.object_name:
            raise ValueError(
                "Source object name is required for full-load execution."
            )

        # A target schema is required for target preparation and writes.
        if not target_object.schema_name:
            raise ValueError(
                "Target schema is required for full-load execution."
            )

        # A target object name is required for target preparation and writes.
        if not target_object.object_name:
            raise ValueError(
                "Target object name is required for full-load execution."
            )

        # ---------------------------------------------------------
        # BUILD FIELD LISTS
        # ---------------------------------------------------------

        # Sort mappings explicitly by metadata ordinal.
        #
        # WHY:
        # ----
        # The source SELECT column order must match the target INSERT
        # column order and the row values returned by the source query.
        ordered_mappings = sorted(
            field_mappings,
            key=lambda mapping_item: mapping_item.ordinal_no,
        )

        # Ensure every mapping is a DIRECT mapping for this first
        # implementation.
        for mapping_item in ordered_mappings:
            if mapping_item.mapping_type_code.upper() != "DIRECT":
                raise ValueError(
                    "FullLoadExecutor currently supports only "
                    "DIRECT field mappings. "
                    f"Mapping field "
                    f"{mapping_item.mapping_field_id} uses "
                    f"'{mapping_item.mapping_type_code}'."
                )

        # Extract source column names in runtime mapping order.
        source_columns = [
            mapping_item.source_field_name
            for mapping_item in ordered_mappings
        ]

        # Extract target column names in the same runtime mapping order.
        target_columns = [
            mapping_item.target_field_name
            for mapping_item in ordered_mappings
        ]

        # ---------------------------------------------------------
        # BUILD SOURCE SELECT
        # ---------------------------------------------------------

        # The source connector is responsible for vendor-specific
        # execution, but the executor must construct a safe logical
        # SELECT statement.
        #
        # The connector implementation currently supports PostgreSQL,
        # so PostgreSQL identifier quoting is appropriate for this POC.
        #
        # IMPORTANT:
        # Values are not concatenated into the SQL.
        # Only metadata-derived identifiers are inserted here.
        select_columns = ", ".join(
            self._quote_identifier(column_name)
            for column_name in source_columns
        )

        # Quote the physical source schema.
        source_schema = self._quote_identifier(
            source_object.schema_name
        )

        # Quote the physical source object.
        source_table = self._quote_identifier(
            source_object.object_name
        )

        # Construct the source extraction query.
        source_query = (
            f"SELECT {select_columns} "
            f"FROM {source_schema}.{source_table}"
        )

        # ---------------------------------------------------------
        # EXECUTION STATE
        # ---------------------------------------------------------

        # Track the total number of rows successfully sent to the
        # target connector.
        total_rows_written = 0

        # Track whether the target transaction has started.
        #
        # WHY:
        # ----
        # We should only attempt rollback when this executor actually
        # entered the target transaction.
        transaction_started = False

        try:
            # -----------------------------------------------------
            # CONNECT SOURCE
            # -----------------------------------------------------

            # Establish the physical source database connection.
            source_connector.connect()

            # -----------------------------------------------------
            # CONNECT TARGET
            # -----------------------------------------------------

            # Establish the physical target database connection.
            target_connector.connect()

            # -----------------------------------------------------
            # START TARGET TRANSACTION
            # -----------------------------------------------------

            # The target transaction contains TRUNCATE plus all
            # INSERT batches.
            target_connector.begin_transaction()

            # Record that rollback is now required if execution fails.
            transaction_started = True

            # -----------------------------------------------------
            # PREPARE TARGET
            # -----------------------------------------------------

            # The current FULL_LOAD configuration uses
            # TRUNCATE_INSERT.
            #
            # Therefore existing target rows are removed before
            # inserting the source dataset.
            target_connector.truncate_table(
                target_schema=target_object.schema_name,
                target_table=target_object.object_name,
            )

            # -----------------------------------------------------
            # READ SOURCE AND WRITE TARGET
            # -----------------------------------------------------

            # Read source records in controlled batches.
            #
            # The connector implementation uses a server-side cursor,
            # preventing the complete source dataset from being loaded
            # into application memory.
            for source_batch in source_connector.read_batches(
                query=source_query,
                batch_size=load_config.batch_size,
            ):
                # Write the current source batch to the target.
                #
                # The field mapping is DIRECT, so the source row order
                # already matches the target column order.
                rows_written = target_connector.write_batch(
                    target_schema=target_object.schema_name,
                    target_table=target_object.object_name,
                    column_names=target_columns,
                    rows=source_batch,
                )

                # Add the current batch count to the execution total.
                total_rows_written += rows_written

            # -----------------------------------------------------
            # COMMIT TARGET TRANSACTION
            # -----------------------------------------------------

            # All source batches completed successfully.
            #
            # Commit the complete target load as one logical operation.
            target_connector.commit()

            # The transaction has been successfully completed, so
            # rollback is no longer required for this execution path.
            transaction_started = False

            # Return the total number of rows written.
            return total_rows_written

        except Exception:
            # -----------------------------------------------------
            # ROLLBACK TARGET TRANSACTION
            # -----------------------------------------------------

            # If the target transaction was started, remove all
            # uncommitted target changes.
            if transaction_started:
                try:
                    target_connector.rollback()
                except Exception:
                    # Do not hide the original execution exception
                    # if rollback itself encounters a problem.
                    pass

            # Re-raise the original exception so the caller receives
            # the actual failure.
            raise

        finally:
            # -----------------------------------------------------
            # CLOSE TARGET CONNECTION
            # -----------------------------------------------------

            # Always release the target database connection.
            #
            # The connector owns the physical connection lifecycle,
            # so the executor delegates cleanup to the connector.
            try:
                target_connector.close()
            except Exception:
                # Connection cleanup should not hide an execution
                # exception that may already be in progress.
                pass

            # -----------------------------------------------------
            # CLOSE SOURCE CONNECTION
            # -----------------------------------------------------

            # Always release the source database connection.
            try:
                source_connector.close()
            except Exception:
                # Connection cleanup should not hide an execution
                # exception that may already be in progress.
                pass

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """
        Safely quote a SQL identifier for the current PostgreSQL POC.

        WHY
        ---
        Schema, table, and column names come from metadata.

        They must therefore be treated as SQL identifiers rather than
        SQL values.

        Example
        -------
        customer_id
            becomes
        "customer_id"

        This prevents malformed SQL when identifiers contain special
        characters and keeps identifier handling separate from value
        parameterization.
        """

        # Validate that the identifier contains a usable value.
        if not identifier or not identifier.strip():
            raise ValueError(
                "SQL identifier must not be empty."
            )

        # Remove accidental surrounding whitespace.
        identifier = identifier.strip()

        # Escape embedded double quotes according to PostgreSQL
        # identifier rules.
        escaped_identifier = identifier.replace(
            '"',
            '""',
        )

        # Return the safely quoted identifier.
        return f'"{escaped_identifier}"'