"""
Customer Runtime Execution Context Test

Purpose
-------
Validates that all runtime components can be combined into one complete
RuntimeExecutionContext for the Customer Full Load pipeline.

The test validates the following runtime flow:

    Pipeline Version
          |
          v
    Runtime Execution Plan
          |
          +----------------------+
          |                      |
          v                      v
    Source Dataset          Target Dataset
          |                      |
          v                      v
    Source Binding          Target Binding
          |                      |
          v                      v
    Connection 1            Connection 11
          |                      |
          v                      v
    PostgreSQLConnector    PostgreSQLConnector
          |                      |
          +----------+-----------+
                     |
                     v
          RuntimeExecutionContext

Important
---------
This test does NOT:

    - open a physical source database connection
    - open a physical target database connection
    - truncate the target table
    - read source data
    - write target data
    - modify metadata

It only validates runtime metadata resolution and connector creation.
"""

# Import the PostgreSQL connector class so that the test can verify that
# the dynamically resolved connectors are the expected implementation.
from app.connectors.postgres.adapter import PostgreSQLConnector

# Import the runtime execution context resolver.
#
# This resolver combines:
#   1. RuntimeMetadataResolver
#   2. RuntimeObjectResolver
#   3. RuntimeConnectionResolver
from app.runtime.context_resolver import RuntimeExecutionContextResolver


def main() -> None:
    """
    Execute the Customer runtime execution-context test.
    """

    # ----------------------------------------------------------------------
    # CUSTOMER POC IDENTIFIERS
    # ----------------------------------------------------------------------
    # These identifiers already exist in the metadata store and were
    # validated during the previous orchestration and runtime tests.

    # Tenant that owns the Customer ingestion configuration.
    tenant_id = 1

    # Exact pipeline version that should be resolved.
    #
    # From the Customer orchestration:
    #
    #   Pipeline ID          : 2
    #   Pipeline Version ID  : 2
    #   Version Number       : 1
    #
    # RuntimeMetadataResolver.resolve() expects the exact
    # pipeline_version_id.
    pipeline_version_id = 2

    # Runtime environment used to resolve the physical dataset bindings.
    environment_id = 1

    # ----------------------------------------------------------------------
    # CREATE CONTEXT RESOLVER
    # ----------------------------------------------------------------------
    # The context resolver internally creates and coordinates:
    #
    #   RuntimeMetadataResolver
    #   RuntimeObjectResolver
    #   RuntimeConnectionResolver
    #
    # No physical database connection is opened at this point.
    resolver = RuntimeExecutionContextResolver()

    print("=" * 100)
    print("CUSTOMER RUNTIME EXECUTION CONTEXT")
    print("=" * 100)

    # ----------------------------------------------------------------------
    # RESOLVE COMPLETE EXECUTION CONTEXT
    # ----------------------------------------------------------------------
    # IMPORTANT:
    # RuntimeMetadataResolver.resolve() accepts:
    #
    #     pipeline_version_id
    #
    # Therefore, we pass the exact pipeline version ID here.
    #
    # tenant_id and environment_id are used by the context resolver when
    # resolving the physical source and target dataset bindings.
    context = resolver.resolve(
        pipeline_version_id=pipeline_version_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    # Store the resolved execution plan in a local variable to make the
    # verification and output sections easier to read.
    execution_plan = context.execution_plan

    # ----------------------------------------------------------------------
    # PIPELINE INFORMATION
    # ----------------------------------------------------------------------
    print()
    print("PIPELINE")
    print("-" * 100)

    # Display the stable pipeline identifier.
    print(
        f"Pipeline ID             : "
        f"{execution_plan.pipeline_id}"
    )

    # Display the metadata-driven pipeline code.
    print(
        f"Pipeline Code           : "
        f"{execution_plan.pipeline_code}"
    )

    # Display the exact pipeline version being executed.
    print(
        f"Pipeline Version ID     : "
        f"{execution_plan.pipeline_version_id}"
    )

    # Display the human-readable version number.
    print(
        f"Pipeline Version        : "
        f"{execution_plan.pipeline_version_no}"
    )

    # Display the current metadata status of the pipeline version.
    print(
        f"Pipeline Version Status : "
        f"{execution_plan.pipeline_version_status}"
    )

    # ----------------------------------------------------------------------
    # TASK INFORMATION
    # ----------------------------------------------------------------------
    # The current Customer POC contains exactly one pipeline task.
    task = execution_plan.task

    print()
    print("TASK")
    print("-" * 100)

    # Display the task identifier.
    print(
        f"Task ID                 : "
        f"{task.task_id}"
    )

    # Display the task code.
    print(
        f"Task Code               : "
        f"{task.task_code}"
    )

    # Display the task type.
    print(
        f"Task Type               : "
        f"{task.task_type_code}"
    )

    # Display the mapping version associated with this task.
    print(
        f"Mapping Version ID      : "
        f"{task.mapping_version_id}"
    )

    # Display the task execution sequence.
    print(
        f"Sequence                : "
        f"{task.sequence_no}"
    )

    # ----------------------------------------------------------------------
    # MAPPING INFORMATION
    # ----------------------------------------------------------------------
    mapping = execution_plan.mapping

    print()
    print("MAPPING")
    print("-" * 100)

    # Display the mapping version used by the task.
    print(
        f"Mapping Version ID      : "
        f"{mapping.mapping_version_id}"
    )

    # Display the source logical dataset ID.
    print(
        f"Source Dataset ID       : "
        f"{mapping.primary_source_dataset_id}"
    )

    # Display the source schema version.
    print(
        f"Source Schema Version   : "
        f"{mapping.primary_source_schema_version_id}"
    )

    # Display the target logical dataset ID.
    print(
        f"Target Dataset ID       : "
        f"{mapping.target_dataset_id}"
    )

    # Display the target schema version.
    print(
        f"Target Schema Version   : "
        f"{mapping.target_schema_version_id}"
    )

    # Display the datatype mapping set.
    print(
        f"Datatype Mapping Set    : "
        f"{mapping.datatype_mapping_set_id}"
    )

    # Display the configured load type.
    print(
        f"Load Type               : "
        f"{mapping.load_type_code}"
    )

    # Display the configured load strategy.
    print(
        f"Load Strategy           : "
        f"{mapping.load_strategy_code}"
    )

    # ----------------------------------------------------------------------
    # LOAD CONFIGURATION
    # ----------------------------------------------------------------------
    load_config = execution_plan.load_config

    print()
    print("LOAD CONFIGURATION")
    print("-" * 100)

    # Display the load configuration identifier.
    print(
        f"Load Config ID          : "
        f"{load_config.load_config_id}"
    )

    # Display the configured batch size.
    print(
        f"Batch Size              : "
        f"{load_config.batch_size}"
    )

    # Display whether the target should be truncated before loading.
    print(
        f"Truncate Before Load    : "
        f"{load_config.truncate_before_load}"
    )

    # Display whether the load configuration is active.
    print(
        f"Active                  : "
        f"{load_config.is_active}"
    )

    # ----------------------------------------------------------------------
    # TARGET CONFIGURATION
    # ----------------------------------------------------------------------
    target_config = execution_plan.target_config

    print()
    print("TARGET CONFIGURATION")
    print("-" * 100)

    # Display the target write method.
    print(
        f"Load Method             : "
        f"{target_config.load_method_code}"
    )

    # Display whether the runtime is allowed to create the target.
    print(
        f"Auto Create Target      : "
        f"{target_config.auto_create_target}"
    )

    # Display the configured target alteration policy.
    print(
        f"Alter Target Policy     : "
        f"{target_config.alter_target_policy_code}"
    )

    # Display the transaction mode.
    print(
        f"Transaction Mode        : "
        f"{target_config.transaction_mode_code}"
    )

    # Display the target write timeout.
    print(
        f"Write Timeout           : "
        f"{target_config.write_timeout_seconds}"
    )

    # Display the target preparation action.
    print(
        f"Prepare Action          : "
        f"{target_config.target_prepare_action_code}"
    )

    # ----------------------------------------------------------------------
    # SOURCE PHYSICAL OBJECT
    # ----------------------------------------------------------------------
    print()
    print("SOURCE OBJECT")
    print("-" * 100)

    # Display the logical source dataset ID.
    print(
        f"Dataset ID              : "
        f"{context.source_object.dataset_id}"
    )

    # Display the physical binding identifier.
    print(
        f"Dataset Binding ID      : "
        f"{context.source_object.dataset_binding_id}"
    )

    # Display the connection profile used by the source.
    print(
        f"Connection ID           : "
        f"{context.source_object.connection_id}"
    )

    # Display the source catalog/database.
    print(
        f"Catalog                 : "
        f"{context.source_object.catalog_name}"
    )

    # Display the source schema.
    print(
        f"Schema                  : "
        f"{context.source_object.schema_name}"
    )

    # Display the source physical object.
    print(
        f"Object                  : "
        f"{context.source_object.object_name}"
    )

    # ----------------------------------------------------------------------
    # TARGET PHYSICAL OBJECT
    # ----------------------------------------------------------------------
    print()
    print("TARGET OBJECT")
    print("-" * 100)

    # Display the logical target dataset ID.
    print(
        f"Dataset ID              : "
        f"{context.target_object.dataset_id}"
    )

    # Display the physical target binding identifier.
    print(
        f"Dataset Binding ID      : "
        f"{context.target_object.dataset_binding_id}"
    )

    # Display the target connection profile.
    print(
        f"Connection ID           : "
        f"{context.target_object.connection_id}"
    )

    # Display the target catalog/database.
    print(
        f"Catalog                 : "
        f"{context.target_object.catalog_name}"
    )

    # Display the target schema.
    print(
        f"Schema                  : "
        f"{context.target_object.schema_name}"
    )

    # Display the target physical table.
    print(
        f"Object                  : "
        f"{context.target_object.object_name}"
    )

    # ----------------------------------------------------------------------
    # SOURCE CONNECTOR
    # ----------------------------------------------------------------------
    print()
    print("SOURCE CONNECTOR")
    print("-" * 100)

    # Display the dynamically created connector class.
    print(
        f"Connector Class         : "
        f"{context.source_connector.__class__.__name__}"
    )

    # Display the connection ID used by the connector.
    print(
        f"Connection ID           : "
        f"{context.source_connector.metadata.connection_id}"
    )

    # Display the connector type resolved from metadata.
    print(
        f"Connector Code          : "
        f"{context.source_connector.metadata.connector_code}"
    )

    # Display the physical source database.
    print(
        f"Database                : "
        f"{context.source_connector.metadata.database_name}"
    )

    # ----------------------------------------------------------------------
    # TARGET CONNECTOR
    # ----------------------------------------------------------------------
    print()
    print("TARGET CONNECTOR")
    print("-" * 100)

    # Display the dynamically created target connector class.
    print(
        f"Connector Class         : "
        f"{context.target_connector.__class__.__name__}"
    )

    # Display the target connection ID.
    print(
        f"Connection ID           : "
        f"{context.target_connector.metadata.connection_id}"
    )

    # Display the target connector type.
    print(
        f"Connector Code          : "
        f"{context.target_connector.metadata.connector_code}"
    )

    # Display the target physical database.
    print(
        f"Database                : "
        f"{context.target_connector.metadata.database_name}"
    )

    # ======================================================================
    # VALIDATION
    # ======================================================================

    # ----------------------------------------------------------------------
    # Validate pipeline metadata
    # ----------------------------------------------------------------------

    # The Customer POC pipeline identity should be pipeline ID 2.
    assert execution_plan.pipeline_id == 2

    # The Customer POC pipeline version should be version ID 2.
    assert execution_plan.pipeline_version_id == 2

    # The pipeline should be version 1.
    assert execution_plan.pipeline_version_no == 1

    # ----------------------------------------------------------------------
    # Validate task metadata
    # ----------------------------------------------------------------------

    # The Customer full-load task should be task ID 2.
    assert task.task_id == 2

    # The task should reference mapping version 2.
    assert task.mapping_version_id == 2

    # The task should be a full-load task.
    assert task.task_type_code == "FULL_LOAD"

    # ----------------------------------------------------------------------
    # Validate mapping metadata
    # ----------------------------------------------------------------------

    # The Customer mapping version should be mapping version 2.
    assert mapping.mapping_version_id == 2

    # The source dataset should be dataset 7.
    assert mapping.primary_source_dataset_id == 7

    # The target dataset should be dataset 8.
    assert mapping.target_dataset_id == 8

    # The configured load type should be FULL.
    assert mapping.load_type_code == "FULL"

    # The configured load strategy should be TRUNCATE_INSERT.
    assert mapping.load_strategy_code == "TRUNCATE_INSERT"

    # ----------------------------------------------------------------------
    # Validate load configuration
    # ----------------------------------------------------------------------

    # The Customer load configuration should be configuration ID 3.
    assert load_config.load_config_id == 3

    # The configured batch size should be 5000.
    assert load_config.batch_size == 5000

    # The current POC requires target preparation through truncation.
    assert load_config.truncate_before_load is True

    # The configuration must be active.
    assert load_config.is_active is True

    # ----------------------------------------------------------------------
    # Validate source physical object
    # ----------------------------------------------------------------------

    # Source dataset 7 should use connection 1.
    assert context.source_object.connection_id == 1

    # Source physical database/catalog.
    assert (
        context.source_object.catalog_name
        == "demo_source_db"
    )

    # Source physical schema.
    assert (
        context.source_object.schema_name
        == "public"
    )

    # Source physical table.
    assert (
        context.source_object.object_name
        == "customer"
    )

    # ----------------------------------------------------------------------
    # Validate target physical object
    # ----------------------------------------------------------------------

    # Target dataset 8 should use connection 11.
    assert context.target_object.connection_id == 11

    # Target physical database/catalog.
    assert (
        context.target_object.catalog_name
        == "ingestion_metastore"
    )

    # Target physical schema.
    assert (
        context.target_object.schema_name
        == "warehouse"
    )

    # Target physical table.
    assert (
        context.target_object.object_name
        == "customer_target"
    )

    # ----------------------------------------------------------------------
    # Validate source connector
    # ----------------------------------------------------------------------

    # The source connector should be the PostgreSQL implementation for
    # the current Customer POC.
    assert isinstance(
        context.source_connector,
        PostgreSQLConnector,
    )

    # The connector must reference the same connection as the source
    # dataset binding.
    assert (
        context.source_connector.metadata.connection_id
        == context.source_object.connection_id
    )

    # The source connector must be PostgreSQL.
    assert (
        context.source_connector.metadata.connector_code
        == "POSTGRESQL_CONNECTOR"
    )

    # The source connector should point to demo_source_db.
    assert (
        context.source_connector.metadata.database_name
        == "demo_source_db"
    )

    # ----------------------------------------------------------------------
    # Validate target connector
    # ----------------------------------------------------------------------

    # The target connector should also be PostgreSQL for this POC.
    assert isinstance(
        context.target_connector,
        PostgreSQLConnector,
    )

    # The connector must reference the same connection as the target
    # dataset binding.
    assert (
        context.target_connector.metadata.connection_id
        == context.target_object.connection_id
    )

    # The target connector must be PostgreSQL.
    assert (
        context.target_connector.metadata.connector_code
        == "POSTGRESQL_CONNECTOR"
    )

    # The target connector should point to ingestion_metastore.
    assert (
        context.target_connector.metadata.database_name
        == "ingestion_metastore"
    )

    # ----------------------------------------------------------------------
    # Final result
    # ----------------------------------------------------------------------
    print()
    print("=" * 100)
    print("RUNTIME EXECUTION CONTEXT PASSED")
    print("=" * 100)

    # Display the resolved execution path so it is easy to verify during
    # development and stand-up/debugging.
    print("Pipeline                 : CUSTOMER_FULL_LOAD_PIPELINE")
    print("Pipeline Version ID      : 2")
    print("Mapping Version ID      : 2")

    print()
    print(
        "Source                   : "
        "demo_source_db.public.customer"
    )

    print(
        "Target                   : "
        "ingestion_metastore.warehouse.customer_target"
    )

    print()
    print("Source Connector         : PostgreSQLConnector")
    print("Target Connector         : PostgreSQLConnector")

    # Explicitly confirm that this test has not opened physical database
    # connections or performed any data movement.
    print()
    print("Physical connections     : NOT OPENED")
    print("Data movement            : NOT PERFORMED")
    print("Metadata modified        : NO")
    print("Operation                : READ ONLY")
    print("=" * 100)


if __name__ == "__main__":
    # Execute the test only when this module is invoked directly.
    main()