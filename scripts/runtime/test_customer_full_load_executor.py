"""
Customer Full Load Executor - Integration Test
===============================================

Purpose
-------
Validates the complete FULL LOAD execution path for the Customer POC.

The test verifies:

    1. Runtime execution context resolution
    2. Runtime field mapping resolution
    3. Source database connection
    4. Target database connection
    5. Target TRUNCATE operation
    6. Source batch reading
    7. Target batch writing
    8. Target transaction commit
    9. Target row-count verification
    10. Optional test-data cleanup

Current Customer POC
--------------------
Source:

    demo_source_db.public.customer

Target:

    ingestion_metastore.warehouse.customer_target

Field mappings:

    customer_id   -> customer_id
    customer_name -> customer_name
    email         -> email
    city          -> city

Important
---------
The FullLoadExecutor owns and commits the target transaction.

Therefore, this test verifies the committed result and then performs
an explicit cleanup so that the development target table is returned
to an empty state.

This is an integration test and therefore performs real source reads
and target writes.
"""

# Import the runtime execution context resolver.
#
# This resolver combines:
#
#     Runtime Execution Plan
#     Source Physical Object
#     Target Physical Object
#     Source Connector
#     Target Connector
#
# It internally creates the required metadata, object, and connection
# resolvers.
from app.runtime.context_resolver import RuntimeExecutionContextResolver

# Import the runtime field mapping resolver.
#
# This resolves the metadata-driven source-to-target field mappings
# from map.mapping_field, map.mapping_field_input, and
# catalog.dataset_field.
from app.runtime.field_mapping_resolver import RuntimeFieldMappingResolver

# Import the Full Load Executor that performs the actual source-to-target
# data movement.
from app.runtime.full_load_executor import FullLoadExecutor


def main() -> None:
    """
    Execute the Customer FULL LOAD integration test.

    The test uses the existing Customer POC metadata:

        Pipeline Version : 2
        Tenant            : 1
        Environment       : 1

    The FullLoadExecutor performs the actual load and commits the
    target transaction.

    After successful verification, the test optionally truncates
    the target again depending on CLEANUP_AFTER_TEST.
    """

    # =============================================================
    # TEST CONFIGURATION
    # =============================================================

    # Existing Customer POC pipeline version.
    pipeline_version_id = 2

    # Existing Customer POC tenant.
    tenant_id = 1

    # Existing Customer POC environment.
    environment_id = 1

    # Existing Customer target physical object.
    target_schema = "warehouse"
    target_table = "customer_target"

    # Controls whether test data is removed after successful verification.
    #
    # True  = integration-test mode; clean the target after verification.
    # False = demo/debug mode; keep the loaded rows in the target table
    #         so they can be inspected after the test completes.
    CLEANUP_AFTER_TEST = False

    # =============================================================
    # CREATE RUNTIME CONTEXT RESOLVER
    # =============================================================

    # Create the resolver responsible for building the complete
    # RuntimeExecutionContext.
    #
    # The resolver internally creates:
    #
    #     RuntimeMetadataResolver
    #     RuntimeObjectResolver
    #     RuntimeConnectionResolver
    #
    # No physical database connection is opened at this stage.
    context_resolver = RuntimeExecutionContextResolver()

    # =============================================================
    # RESOLVE COMPLETE RUNTIME CONTEXT
    # =============================================================

    # Resolve the complete execution context from metadata.
    #
    # This resolves:
    #
    #     Pipeline Version
    #          ↓
    #     Execution Plan
    #          ↓
    #     Source Object
    #          ↓
    #     Target Object
    #          ↓
    #     Source Connector
    #          ↓
    #     Target Connector
    context = context_resolver.resolve(
        pipeline_version_id=pipeline_version_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    # =============================================================
    # RESOLVE FIELD MAPPINGS
    # =============================================================

    # Create the field mapping resolver.
    field_mapping_resolver = RuntimeFieldMappingResolver()

    # Resolve the source-to-target field mappings using the mapping
    # version already resolved inside the execution plan.
    field_mappings = field_mapping_resolver.resolve(
        mapping_version_id=(
            context.execution_plan.mapping.mapping_version_id
        ),
        tenant_id=tenant_id,
    )

    # =============================================================
    # DISPLAY TEST INFORMATION
    # =============================================================

    print("=" * 80)
    print("CUSTOMER FULL LOAD EXECUTOR TEST")
    print("=" * 80)

    print()
    print(
        "Pipeline Version :",
        context.execution_plan.pipeline_version_id,
    )

    print(
        "Mapping Version  :",
        context.execution_plan.mapping.mapping_version_id,
    )

    print(
        "Load Type        :",
        context.execution_plan.mapping.load_type_code,
    )

    print(
        "Load Strategy    :",
        context.execution_plan.mapping.load_strategy_code,
    )

    print(
        "Batch Size       :",
        context.execution_plan.load_config.batch_size,
    )

    print()
    print("Source Object")
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

    print()
    print("Target Object")
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

    print()
    print("Field Mappings")
    print("-" * 80)

    # Display the resolved field mappings in execution order.
    for mapping in field_mappings:
        print(
            f"{mapping.ordinal_no}: "
            f"{mapping.source_field_name} -> "
            f"{mapping.target_field_name} "
            f"[{mapping.mapping_type_code}]"
        )

    # =============================================================
    # CREATE FULL LOAD EXECUTOR
    # =============================================================

    # Create the executor responsible for physical source-to-target
    # data movement.
    executor = FullLoadExecutor()

    # =============================================================
    # EXECUTE FULL LOAD
    # =============================================================

    print()
    print("-" * 80)
    print("STARTING FULL LOAD")
    print("-" * 80)

    # Execute the complete full-load operation.
    #
    # The executor will:
    #
    #     1. Connect to source
    #     2. Connect to target
    #     3. Begin target transaction
    #     4. Truncate target
    #     5. Read source in batches
    #     6. Write batches to target
    #     7. Commit target transaction
    #     8. Close connections
    rows_written = executor.execute(
        context=context,
        field_mappings=field_mappings,
    )

    # =============================================================
    # VERIFY EXECUTION RESULT
    # =============================================================

    print()
    print("-" * 80)
    print("FULL LOAD EXECUTION COMPLETED")
    print("-" * 80)

    print(
        "Rows Written :",
        rows_written,
    )

    # The executor should report at least zero rows.
    #
    # A negative count indicates an invalid executor implementation.
    if rows_written < 0:
        raise AssertionError(
            "Executor returned an invalid negative row count."
        )

    print(
        "Execution Result : PASSED"
    )

    # =============================================================
    # VERIFY TARGET DATA
    # =============================================================

    # The executor closes the target connector in its finally block.
    #
    # Therefore, resolve a fresh target connector through the existing
    # runtime connection resolver for verification.
    from app.runtime.connection_resolver import RuntimeConnectionResolver

    # Create the connection resolver.
    verification_connection_resolver = RuntimeConnectionResolver()

    # Resolve a fresh target connector using the target dataset binding.
    verification_connector = (
        verification_connection_resolver.resolve(
            context.target_object.connection_id
        )
    )

    try:
        # Open the target verification connection.
        verification_connector.connect()

        # Obtain the active connection from the PostgreSQL connector.
        #
        # The current POC uses PostgreSQLConnector, so this verification
        # query is intentionally limited to this integration test.
        connection = verification_connector._require_connection()

        # Query the number of rows currently persisted in the target.
        with connection.cursor() as cursor:

            # Use quoted identifiers because the schema and table names
            # come from runtime metadata.
            cursor.execute(
                f"""
                SELECT COUNT(*)
                FROM "{target_schema}"."{target_table}";
                """
            )

            # Fetch the single COUNT(*) result.
            target_row_count = cursor.fetchone()[0]

        print()
        print(
            "Target Rows After Load :",
            target_row_count,
        )

        # The persisted target row count should equal the number of
        # rows reported by the executor.
        if target_row_count != rows_written:
            raise AssertionError(
                "Target row count does not match executor "
                "reported row count. "
                f"Executor={rows_written}, "
                f"Target={target_row_count}."
            )

        print(
            "Target Row Count Verification : PASSED"
        )

    finally:
        # Always close the verification connector.
        verification_connector.close()

    # =============================================================
    # OPTIONAL TEST DATA CLEANUP
    # =============================================================

    if CLEANUP_AFTER_TEST:
        # The executor intentionally commits the full-load transaction.
        #
        # Therefore, when cleanup is enabled, this test explicitly cleans
        # the target after successful verification.
        #
        # The cleanup uses a fresh connector so it does not depend on
        # the executor's already-closed connector.
        cleanup_connection_resolver = RuntimeConnectionResolver()

        # Resolve another target connector for cleanup.
        cleanup_connector = cleanup_connection_resolver.resolve(
            context.target_object.connection_id
        )

        try:
            # Open the target cleanup connection.
            cleanup_connector.connect()

            # Start a cleanup transaction.
            cleanup_connector.begin_transaction()

            # Remove all test rows from the Customer target.
            cleanup_connector.truncate_table(
                target_schema=target_schema,
                target_table=target_table,
            )

            # Commit the cleanup operation.
            cleanup_connector.commit()

            print(
                "Test Data Cleanup : PASSED"
            )

        except Exception:
            # If cleanup fails, attempt to roll back the cleanup transaction.
            try:
                cleanup_connector.rollback()
            except Exception:
                pass

            # Re-raise the original cleanup error.
            raise

        finally:
            # Always close the cleanup connector.
            cleanup_connector.close()

    else:
        # Demo/debug mode: retain the loaded rows so they can be inspected
        # directly in the target database after the test completes.
        print(
            "Test Data Cleanup : SKIPPED "
            "(CLEANUP_AFTER_TEST=False)"
        )

    # =============================================================
    # FINAL TEST RESULT
    # =============================================================

    print()
    print("=" * 80)
    print("CUSTOMER FULL LOAD EXECUTOR TEST PASSED")
    print("=" * 80)


# Execute the test only when this script is run directly.
if __name__ == "__main__":
    main()