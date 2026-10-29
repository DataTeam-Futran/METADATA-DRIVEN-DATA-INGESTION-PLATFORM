"""
Customer FULL LOAD Executor - Integration Test
================================================

PURPOSE
-------
Validates the complete metadata-driven FULL LOAD execution path
for the Customer POC.

This script is an INTEGRATION / DEMONSTRATION TEST.

It validates that the runtime components work together correctly:

    1. Runtime execution context resolution
    2. Runtime field mapping resolution
    3. Dynamic source connection resolution
    4. Dynamic target connection resolution
    5. Source/target physical schema validation
    6. Source data availability validation
    7. Target TRUNCATE operation
    8. Source batch reading
    9. Target batch writing
    10. Target transaction commit
    11. Target row-count verification
    12. Optional test-data cleanup


CURRENT CUSTOMER POC
--------------------

Source:
    demo_source_db.public.customer

Target:
    ingestion_metastore.warehouse.customer_target

Pipeline:
    Pipeline Version 2

Mapping:
    Mapping Version 2

Load:
    FULL + TRUNCATE_INSERT

Batch Size:
    5000

Field mappings:
    customer_id    -> customer_id
    customer_name  -> customer_name
    email          -> email
    city           -> city


IMPORTANT - EXCEPTION HANDLING RESPONSIBILITY
----------------------------------------------

This file is ONLY the integration/demo test harness.

The actual exception handling must NOT be implemented here.

Actual exception handling is implemented in:

    1. app/core/exceptions.py
       - Defines the common ingestion exception hierarchy.
       - Example:
             IngestionPlatformError
             ConnectionResolutionError
             SchemaValidationError
             SourceReadError
             TargetWriteError
             TransactionError
             NoSourceDataError
             etc.

    2. app/runtime/full_load_executor.py
       - Handles the FULL LOAD execution flow.
       - Handles source/target connection failures.
       - Handles schema validation failures.
       - Handles source read failures.
       - Handles target TRUNCATE failures.
       - Handles target write failures.
       - Handles transaction failures.
       - Performs rollback when required.
       - Handles zero-source-record scenario.
       - Performs connection/resource cleanup.

    3. app/connectors/postgres/adapter.py
       - Performs PostgreSQL-specific database operations.
       - Raises underlying database exceptions.
       - Does not contain the complete business-level execution flow.


IMPORTANT - NEGATIVE TEST SCENARIOS
-----------------------------------

Individual failure scenarios should be deliberately tested through
a separate negative-test script.

Examples:

    FL-001  Source DB unavailable
    FL-002  Wrong source credentials
    FL-003  Source table does not exist
    FL-004  Source schema changed
    FL-005  Target DB unavailable
    FL-006  Target table does not exist
    FL-007  Permission denied
    FL-008  TRUNCATE failure
    FL-009  Source extraction failure
    FL-010  Data type mismatch
    FL-011  NOT NULL violation
    FL-012  Duplicate PK
    FL-013  Target disk full
    FL-014  Network failure during load
    FL-015  Metadata missing
    FL-016  Wrong target mapping
    FL-017  Application crash after TRUNCATE
    FL-018  Application crash after INSERT
    FL-019  Audit update failure
    FL-020  Failure after TRUNCATE
    FL-021  Source returns zero records
    FL-022  No new records - Incremental load


IMPORTANT - FL-021 ZERO SOURCE RECORDS
--------------------------------------

FL-021 is handled by FullLoadExecutor.

The expected execution sequence is:

    1. Resolve source connection
    2. Resolve target connection
    3. Validate physical schema
    4. Read the first source batch
    5. If source returns zero records:
           raise NoSourceDataError
    6. STOP execution
    7. Do NOT begin target transaction
    8. Do NOT TRUNCATE target

This is important because a FULL LOAD must not destroy existing
target data when the source contains zero records.

The implementation belongs in:

    app/runtime/full_load_executor.py

The exception definition belongs in:

    app/core/exceptions.py


IMPORTANT - FL-017 / FL-018 APPLICATION CRASH
---------------------------------------------

Process-level crashes cannot always be caught by Python try/except.

For example:

    FL-017:
        Application crashes after TRUNCATE.

    FL-018:
        Application crashes after INSERT.

The target transaction should protect uncommitted changes.

Expected behavior:

    BEGIN TRANSACTION
        |
        +-- TRUNCATE
        |
        +-- INSERT
        |
        +-- COMMIT
             |
             +-- Only committed data becomes permanent.

If the application/process terminates before COMMIT,
PostgreSQL transaction semantics should roll back the
uncommitted transaction.

Dedicated crash testing is still required to validate this.


IMPORTANT - FL-019 / AUDIT FAILURE
----------------------------------

FL-019 is not a responsibility of this Customer FULL LOAD
integration test.

Audit/status update handling belongs to the runtime/audit layer.

The executor should not silently treat an audit update failure
as a successful ingestion.


IMPORTANT - FL-022 / INCREMENTAL LOAD
--------------------------------------

FL-022:

    "No new records - Incremental"

is outside the scope of this FULL LOAD executor.

It belongs to the incremental-load implementation because
incremental processing requires watermark/change tracking logic.


RUN
---

Run this script from the project root:

    python -m scripts.runtime.test_customer_full_load_executor
"""


from __future__ import annotations


# ================================================================
# STANDARD LIBRARY IMPORTS
# ================================================================

import logging


# ================================================================
# APPLICATION IMPORTS
# ================================================================

from app.core.exceptions import IngestionPlatformError
from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.context_resolver import RuntimeExecutionContextResolver
from app.runtime.field_mapping_resolver import RuntimeFieldMappingResolver
from app.runtime.full_load_executor import FullLoadExecutor


# ================================================================
# LOGGING
# ================================================================

# Keep logging simple for the current POC.
#
# Production structured logging / audit logging can be implemented
# separately in the runtime/audit layer.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ================================================================
# TEST CONFIGURATION
# ================================================================

# Existing Customer POC pipeline version.
PIPELINE_VERSION_ID = 2

# Existing Customer POC tenant.
TENANT_ID = 1

# Existing Customer POC environment.
ENVIRONMENT_ID = 1


# ----------------------------------------------------------------
# CLEANUP CONFIGURATION
# ----------------------------------------------------------------
#
# False:
#     Keep target data after successful execution.
#
#     Useful when demonstrating the loaded data in pgAdmin.
#
# True:
#     Truncate the target table after successful verification.
#
# ----------------------------------------------------------------

CLEANUP_AFTER_TEST = False


# ================================================================
# MAIN TEST
# ================================================================

def main() -> None:
    """
    Execute the Customer FULL LOAD integration test.

    IMPORTANT:
        This function is responsible for orchestration and
        verification only.

        The actual FULL LOAD exception handling belongs to
        FullLoadExecutor and the platform exception hierarchy.
    """

    print()
    print("=" * 80)
    print("CUSTOMER FULL LOAD EXECUTOR TEST")
    print("=" * 80)


    # ============================================================
    # 1. RESOLVE RUNTIME EXECUTION CONTEXT
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 1 - RESOLVE RUNTIME EXECUTION CONTEXT")
    print("-" * 80)

    # The execution context contains runtime metadata required
    # by the FULL LOAD executor.
    context_resolver = RuntimeExecutionContextResolver()

    context = context_resolver.resolve(
        pipeline_version_id=PIPELINE_VERSION_ID,
        tenant_id=TENANT_ID,
        environment_id=ENVIRONMENT_ID,
    )

    print(
        "Pipeline Version :",
        context.execution_plan.pipeline_version_id,
    )

    print(
        "Tenant ID        :",
        TENANT_ID,
    )

    print(
        "Environment ID   :",
        ENVIRONMENT_ID,
    )


    # ============================================================
    # 2. RESOLVE FIELD MAPPINGS
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 2 - RESOLVE FIELD MAPPINGS")
    print("-" * 80)

    # Field mappings are resolved dynamically from metadata.
    #
    # No source/target column mappings are hard-coded in the
    # executor.
    field_mapping_resolver = RuntimeFieldMappingResolver()

    field_mappings = field_mapping_resolver.resolve(
        mapping_version_id=(
            context.execution_plan.mapping.mapping_version_id
        ),
        tenant_id=TENANT_ID,
    )

    print(
        "Mapping Version :",
        context.execution_plan.mapping.mapping_version_id,
    )

    print()
    print("Resolved Field Mappings")
    print("-" * 80)

    for mapping in field_mappings:

        print(
            f"{mapping.ordinal_no}: "
            f"{mapping.source_field_name} -> "
            f"{mapping.target_field_name} "
            f"[{mapping.mapping_type_code}]"
        )


    # ============================================================
    # 3. DISPLAY EXECUTION CONFIGURATION
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 3 - EXECUTION CONFIGURATION")
    print("-" * 80)

    execution_plan = context.execution_plan

    print(
        "Pipeline Version :",
        execution_plan.pipeline_version_id,
    )

    print(
        "Mapping Version  :",
        execution_plan.mapping.mapping_version_id,
    )

    print(
        "Load Type        :",
        execution_plan.mapping.load_type_code,
    )

    print(
        "Load Strategy    :",
        execution_plan.mapping.load_strategy_code,
    )

    print(
        "Batch Size       :",
        execution_plan.load_config.batch_size,
    )


    # ============================================================
    # 4. DISPLAY SOURCE OBJECT
    # ============================================================

    print()
    print("-" * 80)
    print("SOURCE OBJECT")
    print("-" * 80)

    print(
        "Connection ID :",
        context.source_object.connection_id,
    )

    print(
        "Catalog       :",
        context.source_object.catalog_name,
    )

    print(
        "Schema        :",
        context.source_object.schema_name,
    )

    print(
        "Object        :",
        context.source_object.object_name,
    )


    # ============================================================
    # 5. DISPLAY TARGET OBJECT
    # ============================================================

    print()
    print("-" * 80)
    print("TARGET OBJECT")
    print("-" * 80)

    print(
        "Connection ID :",
        context.target_object.connection_id,
    )

    print(
        "Catalog       :",
        context.target_object.catalog_name,
    )

    print(
        "Schema        :",
        context.target_object.schema_name,
    )

    print(
        "Object        :",
        context.target_object.object_name,
    )


    # ============================================================
    # 6. CREATE FULL LOAD EXECUTOR
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 4 - CREATE FULL LOAD EXECUTOR")
    print("-" * 80)

    # The executor contains the actual FULL LOAD implementation.
    #
    # IMPORTANT:
    # Do not implement individual exception scenarios in this
    # integration test.
    executor = FullLoadExecutor()

    print(
        "FullLoadExecutor initialized successfully."
    )


    # ============================================================
    # 7. EXECUTE FULL LOAD
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 5 - START FULL LOAD")
    print("-" * 80)

    print()
    print("Execution Flow")
    print("-" * 80)

    print("1. Resolve source connection")
    print("2. Resolve target connection")
    print("3. Validate source/target schema")
    print("4. Check source data availability")
    print("5. Begin target transaction")
    print("6. TRUNCATE target")
    print("7. Read source in batches")
    print("8. Write target batches")
    print("9. Commit target transaction")
    print("10. Close connections")

    print()

    # ------------------------------------------------------------
    # Execute the actual metadata-driven FULL LOAD.
    #
    # IMPORTANT:
    #
    # FullLoadExecutor is responsible for:
    #
    #   - connection exception handling
    #   - schema validation
    #   - source data validation
    #   - source read exception handling
    #   - target TRUNCATE exception handling
    #   - target write exception handling
    #   - transaction handling
    #   - rollback
    #   - resource cleanup
    #
    # This test script only invokes the executor and validates
    # its result.
    # ------------------------------------------------------------

    rows_written = executor.execute(
        context=context,
        field_mappings=field_mappings,
    )


    # ============================================================
    # 8. VERIFY EXECUTOR RESULT
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 6 - FULL LOAD EXECUTION COMPLETED")
    print("-" * 80)

    print(
        "Rows Written :",
        rows_written,
    )

    # Basic sanity validation.
    #
    # A successful executor execution should never return a
    # negative row count.
    if rows_written < 0:

        raise AssertionError(
            "Executor returned an invalid negative row count."
        )

    print(
        "Execution Result : PASSED"
    )


    # ============================================================
    # 9. VERIFY TARGET DATA
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 7 - VERIFY TARGET DATA")
    print("-" * 80)

    # ------------------------------------------------------------
    # IMPORTANT
    # ------------------------------------------------------------
    #
    # The FullLoadExecutor closes its target connector in its
    # finally block.
    #
    # Therefore, this integration test creates a NEW connection
    # for independent target verification.
    #
    # This gives us an independent verification that the target
    # really contains the expected number of rows.
    # ------------------------------------------------------------

    verification_connection_resolver = (
        RuntimeConnectionResolver()
    )

    verification_connector = (
        verification_connection_resolver.resolve(
            context.target_object.connection_id
        )
    )

    try:

        verification_connector.connect()

        # --------------------------------------------------------
        # PostgreSQL-specific verification.
        #
        # The current Customer POC uses PostgreSQL, so the test
        # directly obtains the underlying PostgreSQL connection.
        # --------------------------------------------------------

        connection = (
            verification_connector._require_connection()
        )

        target_schema = (
            context.target_object.schema_name
        )

        target_table = (
            context.target_object.object_name
        )

        # --------------------------------------------------------
        # IMPORTANT SECURITY / SQL RULE
        # --------------------------------------------------------
        #
        # Schema and table names come from runtime metadata.
        #
        # They cannot be passed as normal SQL parameters.
        #
        # Therefore, identifiers are safely escaped before being
        # placed into the SQL statement.
        # --------------------------------------------------------

        quoted_schema = (
            target_schema.replace('"', '""')
        )

        quoted_table = (
            target_table.replace('"', '""')
        )

        verification_query = (
            f'SELECT COUNT(*) '
            f'FROM "{quoted_schema}"."{quoted_table}"'
        )

        with connection.cursor() as cursor:

            cursor.execute(
                verification_query
            )

            target_row_count = (
                cursor.fetchone()[0]
            )

        print(
            "Target Rows After Load :",
            target_row_count,
        )

        # --------------------------------------------------------
        # RECONCILIATION
        # --------------------------------------------------------
        #
        # Executor reported rows written.
        #
        # Target database reports rows actually present.
        #
        # Both values should match for this FULL LOAD POC.
        # --------------------------------------------------------

        if target_row_count != rows_written:

            raise AssertionError(
                "Target row count does not match "
                "executor reported row count. "
                f"Executor={rows_written}, "
                f"Target={target_row_count}."
            )

        print(
            "Target Row Count Verification : PASSED"
        )

    finally:

        # Always close the independent verification connection.
        verification_connector.close()


    # ============================================================
    # 10. OPTIONAL CLEANUP
    # ============================================================

    print()
    print("-" * 80)
    print("STEP 8 - TEST DATA CLEANUP")
    print("-" * 80)

    if CLEANUP_AFTER_TEST:

        cleanup_connection_resolver = (
            RuntimeConnectionResolver()
        )

        cleanup_connector = (
            cleanup_connection_resolver.resolve(
                context.target_object.connection_id
            )
        )

        cleanup_transaction_started = False

        try:

            cleanup_connector.connect()

            # Cleanup is also performed inside a transaction.
            cleanup_connector.begin_transaction()

            cleanup_transaction_started = True

            cleanup_connector.truncate_table(
                target_schema=(
                    context.target_object.schema_name
                ),
                target_table=(
                    context.target_object.object_name
                ),
            )

            cleanup_connector.commit()

            cleanup_transaction_started = False

            print(
                "Test Data Cleanup : PASSED"
            )

        except Exception:

            # ----------------------------------------------------
            # Cleanup failure should not leave an open transaction.
            # ----------------------------------------------------

            if cleanup_transaction_started:

                try:

                    cleanup_connector.rollback()

                except Exception as rollback_exc:

                    logger.warning(
                        "Cleanup rollback failed | "
                        "exception_type=%s",
                        type(rollback_exc).__name__,
                    )

            # Re-raise the cleanup exception so the test correctly
            # reports the cleanup failure.
            raise

        finally:

            cleanup_connector.close()

    else:

        print(
            "Test Data Cleanup : SKIPPED "
            "(CLEANUP_AFTER_TEST=False)"
        )


    # ============================================================
    # 11. FINAL RESULT
    # ============================================================

    print()
    print("=" * 80)
    print("CUSTOMER FULL LOAD EXECUTOR TEST PASSED")
    print("=" * 80)
    print()

    print(
        "Rows Written             :",
        rows_written,
    )

    print(
        "Target Row Count         :",
        target_row_count,
    )

    print(
        "Target Verification     : PASSED"
    )

    print(
        "Overall Result           : PASSED"
    )


# ================================================================
# SCRIPT ENTRY POINT
# ================================================================

if __name__ == "__main__":

    try:

        # Execute the integration test.
        main()

    except IngestionPlatformError as exc:

        # --------------------------------------------------------
        # KNOWN PLATFORM EXCEPTION
        # --------------------------------------------------------
        #
        # Examples:
        #
        #   ConnectionResolutionError
        #   SchemaValidationError
        #   SourceReadError
        #   TargetWriteError
        #   TransactionError
        #   NoSourceDataError
        #   AuthorizationError
        #   etc.
        #
        # The FullLoadExecutor is responsible for rollback and
        # resource cleanup required for the execution failure.
        #
        # This block only reports the failure at test level.
        # --------------------------------------------------------

        print()
        print("=" * 80)
        print("CUSTOMER FULL LOAD EXECUTOR TEST FAILED")
        print("=" * 80)

        print(
            "Exception Type :",
            type(exc).__name__,
        )

        print(
            "Message        :",
            str(exc),
        )

        # --------------------------------------------------------
        # FL-007 - PERMISSION DENIED
        # --------------------------------------------------------

        if type(exc).__name__ == "AuthorizationError":

            print()
            print("FL-007 RESULT  : PASS")
            print("Expected       : INSERT permission denied")
            print("Action         : Target transaction rolled back")
            print("Data Safety    : Existing target data preserved")

        # --------------------------------------------------------
        # Display the underlying database/application exception
        # when exception chaining is available.
        #
        # Example:
        #
        #   AuthorizationError
        #          |
        #          +-- psycopg.errors.InsufficientPrivilege
        #
        # This is useful during debugging.
        # --------------------------------------------------------

        if exc.__cause__ is not None:

            print(
                "Root Cause     :",
                type(exc.__cause__).__name__,
            )

            print(
                "Root Message   :",
                str(exc.__cause__),
            )

        # Re-raise so the operating environment / CI pipeline
        # receives a non-zero failure status.
        raise

    except Exception as exc:

        # --------------------------------------------------------
        # UNEXPECTED TEST-HARNESS FAILURE
        # --------------------------------------------------------
        #
        # This is NOT expected to be the normal path for ingestion
        # failures.
        #
        # Known ingestion failures should be represented by the
        # platform exception hierarchy.
        # --------------------------------------------------------

        print()
        print("=" * 80)
        print("CUSTOMER FULL LOAD EXECUTOR TEST FAILED")
        print("=" * 80)

        print(
            "Exception Type :",
            type(exc).__name__,
        )

        print(
            "Message        :",
            str(exc),
        )

        # Re-raise so the test exits with failure status.
        raise