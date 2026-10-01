"""
Test Customer Runtime Execution Plan
=====================================

Purpose
-------
Verify that the runtime metadata resolver can convert:

    pipeline_version_id = 2

into a complete RuntimeExecutionPlan.

This test is READ ONLY.

It does not:
    - create pipeline runs
    - modify metadata
    - connect to source data
    - connect to target data
    - move any customer records
"""

# Import the runtime metadata resolver.
from app.runtime.metadata_resolver import RuntimeMetadataResolver


# Pipeline version that was created for the Customer full-load POC.
PIPELINE_VERSION_ID = 2


def main() -> None:
    """
    Resolve and display the Customer runtime execution plan.
    """

    print("=" * 100)
    print("CUSTOMER RUNTIME EXECUTION PLAN")
    print("=" * 100)

    # Create the metadata resolver.
    resolver = RuntimeMetadataResolver()

    # Resolve the complete execution plan from pipeline version 2.
    execution_plan = resolver.resolve(
        PIPELINE_VERSION_ID
    )

    # ----------------------------------------------------------------------
    # Display pipeline information
    # ----------------------------------------------------------------------
    print()
    print("PIPELINE")
    print(f"  Pipeline ID         : {execution_plan.pipeline_id}")
    print(f"  Pipeline Code       : {execution_plan.pipeline_code}")
    print(f"  Pipeline Name       : {execution_plan.pipeline_name}")
    print(
        f"  Pipeline Version ID : "
        f"{execution_plan.pipeline_version_id}"
    )
    print(
        f"  Version Number      : "
        f"{execution_plan.pipeline_version_no}"
    )
    print(
        f"  Version Status      : "
        f"{execution_plan.pipeline_version_status}"
    )

    # ----------------------------------------------------------------------
    # Display task information
    # ----------------------------------------------------------------------
    print()
    print("TASK")
    print(f"  Task ID             : {execution_plan.task.task_id}")
    print(f"  Task Code           : {execution_plan.task.task_code}")
    print(f"  Task Type           : {execution_plan.task.task_type_code}")
    print(
        f"  Mapping Version ID  : "
        f"{execution_plan.task.mapping_version_id}"
    )
    print(f"  Sequence            : {execution_plan.task.sequence_no}")
    print(
        f"  Timeout Seconds     : "
        f"{execution_plan.task.timeout_seconds}"
    )

    # ----------------------------------------------------------------------
    # Display mapping information
    # ----------------------------------------------------------------------
    print()
    print("MAPPING")
    print(
        f"  Mapping Version ID       : "
        f"{execution_plan.mapping.mapping_version_id}"
    )
    print(
        f"  Mapping ID               : "
        f"{execution_plan.mapping.mapping_id}"
    )
    print(
        f"  Source Dataset ID        : "
        f"{execution_plan.mapping.primary_source_dataset_id}"
    )
    print(
        f"  Source Schema Version ID : "
        f"{execution_plan.mapping.primary_source_schema_version_id}"
    )
    print(
        f"  Target Dataset ID        : "
        f"{execution_plan.mapping.target_dataset_id}"
    )
    print(
        f"  Target Schema Version ID : "
        f"{execution_plan.mapping.target_schema_version_id}"
    )
    print(
        f"  Datatype Mapping Set     : "
        f"{execution_plan.mapping.datatype_mapping_set_id}"
    )
    print(
        f"  Load Type                : "
        f"{execution_plan.mapping.load_type_code}"
    )
    print(
        f"  Load Strategy            : "
        f"{execution_plan.mapping.load_strategy_code}"
    )

    # ----------------------------------------------------------------------
    # Display load configuration
    # ----------------------------------------------------------------------
    print()
    print("LOAD CONFIGURATION")
    print(
        f"  Load Config ID        : "
        f"{execution_plan.load_config.load_config_id}"
    )
    print(
        f"  Batch Size            : "
        f"{execution_plan.load_config.batch_size}"
    )
    print(
        f"  Truncate Before Load  : "
        f"{execution_plan.load_config.truncate_before_load}"
    )
    print(
        f"  Active                : "
        f"{execution_plan.load_config.is_active}"
    )

    # ----------------------------------------------------------------------
    # Display target configuration
    # ----------------------------------------------------------------------
    print()
    print("TARGET CONFIGURATION")
    print(
        f"  Load Method           : "
        f"{execution_plan.target_config.load_method_code}"
    )
    print(
        f"  Auto Create Target    : "
        f"{execution_plan.target_config.auto_create_target}"
    )
    print(
        f"  Alter Target Policy   : "
        f"{execution_plan.target_config.alter_target_policy_code}"
    )
    print(
        f"  Transaction Mode      : "
        f"{execution_plan.target_config.transaction_mode_code}"
    )
    print(
        f"  Write Timeout         : "
        f"{execution_plan.target_config.write_timeout_seconds}"
    )
    print(
        f"  Prepare Action        : "
        f"{execution_plan.target_config.target_prepare_action_code}"
    )

    # ----------------------------------------------------------------------
    # Validate the critical runtime relationships
    # ----------------------------------------------------------------------
    # These assertions prove that the runtime resolver did not accidentally
    # disconnect the task, mapping, or configuration objects.
    assert execution_plan.pipeline_version_id == PIPELINE_VERSION_ID
    assert execution_plan.task.mapping_version_id == 2
    assert execution_plan.mapping.mapping_version_id == 2
    assert execution_plan.load_config.mapping_version_id == 2
    assert execution_plan.target_config.mapping_version_id == 2

    # Confirm that this is the expected Customer full-load configuration.
    assert execution_plan.task.task_type_code == "FULL_LOAD"
    assert execution_plan.mapping.load_type_code == "FULL"
    assert execution_plan.mapping.load_strategy_code == "TRUNCATE_INSERT"

    print()
    print("=" * 100)
    print("RUNTIME EXECUTION PLAN RESOLUTION PASSED")
    print("=" * 100)
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()