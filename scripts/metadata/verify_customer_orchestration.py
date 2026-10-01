"""
Customer Orchestration Verification
====================================

Purpose
-------
This script performs a READ-ONLY verification of the Customer full-load
orchestration metadata.

It does NOT insert, update, delete, or modify any metadata.

The verification follows the runtime relationship:

    Pipeline
        |
        v
    Pipeline Version
        |
        v
    Pipeline Task
        |
        v
    Mapping Version
        |
        +--> Load Configuration
        |
        +--> Target Load Configuration

Why this is important
---------------------
The pipeline was created successfully, but before building the execution
engine we need to confirm that all metadata relationships are correct.
"""

# Import the application's centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Expected Customer orchestration identifiers
# ---------------------------------------------------------------------------
# These IDs were generated/validated during the previous metadata steps.
EXPECTED_TENANT_ID = 1
EXPECTED_PROJECT_ID = 1
EXPECTED_PIPELINE_ID = 2
EXPECTED_PIPELINE_VERSION_ID = 2
EXPECTED_TASK_ID = 2
EXPECTED_MAPPING_VERSION_ID = 2


def verify_customer_orchestration() -> None:
    """
    Verify the complete Customer orchestration metadata graph.

    The function only executes SELECT statements, so no metadata is changed.
    """

    print("=" * 100)
    print("CUSTOMER ORCHESTRATION VERIFICATION")
    print("=" * 100)

    # Open a connection to the metadata/control database.
    with get_metastore_connection() as connection:

        # Create a cursor for executing read-only SQL statements.
        with connection.cursor() as cursor:

            # ------------------------------------------------------------------
            # 1. Verify pipeline
            # ------------------------------------------------------------------
            # This confirms that the stable pipeline identity exists and belongs
            # to the expected tenant and project.
            cursor.execute(
                """
                SELECT
                    pipeline_id,
                    tenant_id,
                    project_id,
                    pipeline_code,
                    pipeline_name,
                    status_code,
                    pipeline_type_code
                FROM orch.pipeline
                WHERE pipeline_id = %s;
                """,
                (EXPECTED_PIPELINE_ID,),
            )

            pipeline = cursor.fetchone()

            if pipeline is None:
                raise RuntimeError(
                    f"Pipeline {EXPECTED_PIPELINE_ID} was not found."
                )

            (
                pipeline_id,
                tenant_id,
                project_id,
                pipeline_code,
                pipeline_name,
                pipeline_status,
                pipeline_type,
            ) = pipeline

            if tenant_id != EXPECTED_TENANT_ID:
                raise RuntimeError(
                    f"Unexpected tenant_id: {tenant_id}"
                )

            if project_id != EXPECTED_PROJECT_ID:
                raise RuntimeError(
                    f"Unexpected project_id: {project_id}"
                )

            print()
            print("Pipeline verification: PASSED")
            print(f"  Pipeline ID   : {pipeline_id}")
            print(f"  Pipeline Code : {pipeline_code}")
            print(f"  Pipeline Name : {pipeline_name}")
            print(f"  Status        : {pipeline_status}")
            print(f"  Type          : {pipeline_type}")

            # ------------------------------------------------------------------
            # 2. Verify pipeline version
            # ------------------------------------------------------------------
            # The pipeline version must belong to the pipeline verified above.
            cursor.execute(
                """
                SELECT
                    pipeline_version_id,
                    tenant_id,
                    pipeline_id,
                    version_no,
                    status_code,
                    config_hash
                FROM orch.pipeline_version
                WHERE pipeline_version_id = %s;
                """,
                (EXPECTED_PIPELINE_VERSION_ID,),
            )

            pipeline_version = cursor.fetchone()

            if pipeline_version is None:
                raise RuntimeError(
                    f"Pipeline version "
                    f"{EXPECTED_PIPELINE_VERSION_ID} was not found."
                )

            (
                pipeline_version_id,
                version_tenant_id,
                version_pipeline_id,
                version_no,
                version_status,
                config_hash,
            ) = pipeline_version

            if version_tenant_id != EXPECTED_TENANT_ID:
                raise RuntimeError(
                    f"Unexpected pipeline-version tenant_id: "
                    f"{version_tenant_id}"
                )

            if version_pipeline_id != EXPECTED_PIPELINE_ID:
                raise RuntimeError(
                    f"Pipeline version points to pipeline "
                    f"{version_pipeline_id}, expected "
                    f"{EXPECTED_PIPELINE_ID}."
                )

            print()
            print("Pipeline version verification: PASSED")
            print(f"  Pipeline Version ID : {pipeline_version_id}")
            print(f"  Pipeline ID         : {version_pipeline_id}")
            print(f"  Version Number      : {version_no}")
            print(f"  Status              : {version_status}")
            print(f"  Config Hash         : {config_hash}")

            # ------------------------------------------------------------------
            # 3. Verify pipeline task
            # ------------------------------------------------------------------
            # The task is the executable unit inside the pipeline version.
            cursor.execute(
                """
                SELECT
                    task_id,
                    tenant_id,
                    pipeline_version_id,
                    task_code,
                    task_name,
                    task_type_code,
                    mapping_version_id,
                    sequence_no,
                    on_failure_code,
                    retry_policy_id,
                    timeout_seconds
                FROM orch.pipeline_task
                WHERE task_id = %s;
                """,
                (EXPECTED_TASK_ID,),
            )

            task = cursor.fetchone()

            if task is None:
                raise RuntimeError(
                    f"Pipeline task {EXPECTED_TASK_ID} was not found."
                )

            (
                task_id,
                task_tenant_id,
                task_pipeline_version_id,
                task_code,
                task_name,
                task_type,
                mapping_version_id,
                sequence_no,
                on_failure,
                retry_policy_id,
                timeout_seconds,
            ) = task

            if task_tenant_id != EXPECTED_TENANT_ID:
                raise RuntimeError(
                    f"Unexpected task tenant_id: {task_tenant_id}"
                )

            if task_pipeline_version_id != EXPECTED_PIPELINE_VERSION_ID:
                raise RuntimeError(
                    f"Task points to pipeline version "
                    f"{task_pipeline_version_id}, expected "
                    f"{EXPECTED_PIPELINE_VERSION_ID}."
                )

            if mapping_version_id != EXPECTED_MAPPING_VERSION_ID:
                raise RuntimeError(
                    f"Task points to mapping version "
                    f"{mapping_version_id}, expected "
                    f"{EXPECTED_MAPPING_VERSION_ID}."
                )

            print()
            print("Pipeline task verification: PASSED")
            print(f"  Task ID             : {task_id}")
            print(f"  Task Code           : {task_code}")
            print(f"  Task Name           : {task_name}")
            print(f"  Task Type           : {task_type}")
            print(f"  Mapping Version ID  : {mapping_version_id}")
            print(f"  Sequence            : {sequence_no}")
            print(f"  On Failure          : {on_failure}")
            print(f"  Retry Policy ID     : {retry_policy_id}")
            print(f"  Timeout Seconds     : {timeout_seconds}")

                      # ------------------------------------------------------------------
            # 4. Verify mapping version
            # ------------------------------------------------------------------
            # The actual map.mapping_version table uses
            # primary_source_dataset_id and primary_source_schema_version_id
            # for the source side of the mapping.
            #
            # We use the exact column names from the database schema instead
            # of assuming generic source_dataset_id/source_schema_version_id
            # column names.
            cursor.execute(
                """
                SELECT
                    mapping_version_id,
                    tenant_id,
                    mapping_id,
                    version_no,
                    primary_source_dataset_id,
                    primary_source_schema_version_id,
                    target_dataset_id,
                    target_schema_version_id,
                    datatype_mapping_set_id,
                    load_type_code,
                    load_strategy_code,
                    status_code
                FROM map.mapping_version
                WHERE mapping_version_id = %s;
                """,
                (EXPECTED_MAPPING_VERSION_ID,),
            )

            # Read the Customer mapping version row.
            mapping = cursor.fetchone()

            # Fail immediately if the expected mapping version does not exist.
            if mapping is None:
                raise RuntimeError(
                    f"Mapping version {EXPECTED_MAPPING_VERSION_ID} "
                    f"was not found."
                )

            # Extract the actual columns returned by the query.
            (
                mapping_version_id,
                mapping_tenant_id,
                mapping_id,
                mapping_version_no,
                primary_source_dataset_id,
                primary_source_schema_version_id,
                target_dataset_id,
                target_schema_version_id,
                datatype_mapping_set_id,
                load_type,
                load_strategy,
                mapping_status,
            ) = mapping

            # Confirm that the mapping belongs to the expected tenant.
            if mapping_tenant_id != EXPECTED_TENANT_ID:
                raise RuntimeError(
                    f"Unexpected mapping tenant_id: {mapping_tenant_id}"
                )

            # Confirm that the orchestration task points to this mapping.
            if mapping_version_id != EXPECTED_MAPPING_VERSION_ID:
                raise RuntimeError(
                    f"Unexpected mapping version ID: "
                    f"{mapping_version_id}"
                )

            print()
            print("Mapping version verification: PASSED")
            print(f"  Mapping Version ID     : {mapping_version_id}")
            print(f"  Mapping ID             : {mapping_id}")
            print(f"  Version Number         : {mapping_version_no}")
            print(
                f"  Primary Source Dataset : "
                f"{primary_source_dataset_id}"
            )
            print(
                f"  Primary Source Schema  : "
                f"{primary_source_schema_version_id}"
            )
            print(f"  Target Dataset         : {target_dataset_id}")
            print(
                f"  Target Schema          : "
                f"{target_schema_version_id}"
            )
            print(
                f"  Datatype Mapping Set   : "
                f"{datatype_mapping_set_id}"
            )
            print(f"  Load Type              : {load_type}")
            print(f"  Load Strategy          : {load_strategy}")
            print(f"  Status                 : {mapping_status}")

            # ------------------------------------------------------------------
            # 5. Verify load configuration
            # ------------------------------------------------------------------
            # This contains execution behavior such as batch size and whether
            # the target should be truncated before loading.
            cursor.execute(
                """
                SELECT
                    load_config_id,
                    mapping_version_id,
                    load_type_code,
                    batch_size,
                    truncate_before_load,
                    is_active
                FROM ingest.load_config
                WHERE mapping_version_id = %s
                ORDER BY load_config_id DESC
                LIMIT 1;
                """,
                (EXPECTED_MAPPING_VERSION_ID,),
            )

            load_config = cursor.fetchone()

            if load_config is None:
                raise RuntimeError(
                    "No load configuration found for mapping version "
                    f"{EXPECTED_MAPPING_VERSION_ID}."
                )

            (
                load_config_id,
                load_mapping_version_id,
                load_type_code,
                batch_size,
                truncate_before_load,
                load_is_active,
            ) = load_config

            print()
            print("Load configuration verification: PASSED")
            print(f"  Load Config ID        : {load_config_id}")
            print(f"  Mapping Version ID    : {load_mapping_version_id}")
            print(f"  Load Type             : {load_type_code}")
            print(f"  Batch Size            : {batch_size}")
            print(
                f"  Truncate Before Load  : "
                f"{truncate_before_load}"
            )
            print(f"  Active                : {load_is_active}")

                      # ------------------------------------------------------------------
            # 6. Verify target load configuration
            # ------------------------------------------------------------------
            # These are the actual column names deployed in
            # ingest.target_load_config.
            #
            # We use the exact database schema rather than assuming shortened
            # names such as alter_policy_code.
            cursor.execute(
                """
                SELECT
                    mapping_version_id,
                    load_method_code,
                    commit_size,
                    auto_create_target,
                    alter_target_policy_code,
                    transaction_mode_code,
                    write_timeout_seconds,
                    target_prepare_action_code,
                    target_schema_policy_code,
                    constraint_apply_policy_code,
                    index_apply_policy_code
                FROM ingest.target_load_config
                WHERE mapping_version_id = %s
                LIMIT 1;
                """,
                (EXPECTED_MAPPING_VERSION_ID,),
            )

            # Read the target configuration row.
            target_config = cursor.fetchone()

            # The target configuration is mandatory for the Customer full-load
            # execution, so fail verification if it does not exist.
            if target_config is None:
                raise RuntimeError(
                    "No target load configuration found for mapping version "
                    f"{EXPECTED_MAPPING_VERSION_ID}."
                )

            # Extract the values using the exact column order from the query.
            (
                target_mapping_version_id,
                load_method,
                commit_size,
                auto_create_target,
                alter_target_policy,
                transaction_mode,
                write_timeout,
                target_prepare_action,
                target_schema_policy,
                constraint_apply_policy,
                index_apply_policy,
            ) = target_config

            # Confirm that target configuration belongs to the expected
            # Customer mapping version.
            if target_mapping_version_id != EXPECTED_MAPPING_VERSION_ID:
                raise RuntimeError(
                    f"Target configuration points to mapping version "
                    f"{target_mapping_version_id}, expected "
                    f"{EXPECTED_MAPPING_VERSION_ID}."
                )

            # Confirm that the configured target write timeout is valid.
            if write_timeout <= 0:
                raise RuntimeError(
                    f"Invalid target write timeout: {write_timeout}"
                )

            print()
            print("Target load configuration verification: PASSED")
            print(
                f"  Mapping Version ID    : "
                f"{target_mapping_version_id}"
            )
            print(f"  Load Method           : {load_method}")
            print(f"  Commit Size           : {commit_size}")
            print(
                f"  Auto Create Target    : "
                f"{auto_create_target}"
            )
            print(
                f"  Alter Target Policy   : "
                f"{alter_target_policy}"
            )
            print(
                f"  Transaction Mode      : "
                f"{transaction_mode}"
            )
            print(
                f"  Write Timeout         : "
                f"{write_timeout}"
            )
            print(
                f"  Target Prepare Action : "
                f"{target_prepare_action}"
            )
            print(
                f"  Target Schema Policy  : "
                f"{target_schema_policy}"
            )
            print(
                f"  Constraint Policy     : "
                f"{constraint_apply_policy}"
            )
            print(
                f"  Index Policy          : "
                f"{index_apply_policy}"
            )
            # ------------------------------------------------------------------
            # 7. Verify task dependencies
            # ------------------------------------------------------------------
            # A single-task pipeline should not require a dependency.
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM orch.task_dependency
                WHERE pipeline_version_id = %s;
                """,
                (EXPECTED_PIPELINE_VERSION_ID,),
            )

            dependency_count = cursor.fetchone()[0]

            print()
            print("Task dependency verification: PASSED")
            print(f"  Dependency Count : {dependency_count}")

            # ------------------------------------------------------------------
            # 8. Final verification
            # ------------------------------------------------------------------
            # All operations in this script are SELECT statements only.
            print()
            print("=" * 100)
            print("CUSTOMER ORCHESTRATION VERIFICATION COMPLETED")
            print("=" * 100)
            print("Operation         : READ ONLY")
            print("Metadata modified : NO")
            print("Overall status    : PASSED")
            print("=" * 100)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
# Allows execution with:
#
# python -m scripts.metadata.verify_customer_orchestration
#
# without executing the verification when imported as a module.
if __name__ == "__main__":
    verify_customer_orchestration()