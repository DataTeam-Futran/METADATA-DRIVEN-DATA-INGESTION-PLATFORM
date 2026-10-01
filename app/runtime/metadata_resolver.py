"""
Runtime Metadata Resolver
=========================

Purpose
-------
Resolve the metadata required to execute a pipeline task.

Input
-----
pipeline_version_id

Output
------
RuntimeExecutionPlan

The resolver reads:

    orch.pipeline
    orch.pipeline_version
    orch.pipeline_task
    map.mapping_version
    ingest.load_config
    ingest.target_load_config

Important
---------
This component performs metadata resolution only.

It does NOT:
    - connect to the source database
    - connect to the target database
    - read source data
    - write target data
    - create runtime execution records

Those responsibilities belong to later runtime components.
"""

# Import the runtime model objects returned by this resolver.
from app.runtime.models import (
    RuntimeExecutionPlan,
    RuntimeLoadConfig,
    RuntimeMapping,
    RuntimeTargetConfig,
    RuntimeTask,
)

# Reuse the application's central metadata-store connection manager.
from app.db.metastore import get_metastore_connection


class RuntimeMetadataResolver:
    """
    Resolves a pipeline version into a complete runtime execution plan.
    """

    def resolve(self, pipeline_version_id: int) -> RuntimeExecutionPlan:
        """
        Resolve all metadata required to execute one pipeline version.

        Parameters
        ----------
        pipeline_version_id:
            The pipeline version that the runtime should execute.

        Returns
        -------
        RuntimeExecutionPlan
            Fully resolved execution metadata.

        Raises
        ------
        ValueError
            If the supplied ID is invalid.

        LookupError
            If required metadata is missing.
        """

        # Validate the identifier before querying PostgreSQL.
        if pipeline_version_id <= 0:
            raise ValueError(
                "pipeline_version_id must be greater than zero."
            )

        # Open one metadata-store connection for the complete resolution.
        with get_metastore_connection() as connection:

            # Use one cursor for all metadata queries.
            with connection.cursor() as cursor:

                # --------------------------------------------------------------
                # 1. Resolve pipeline version + pipeline
                # --------------------------------------------------------------
                # This establishes the stable pipeline identity and the exact
                # version being executed.
                cursor.execute(
                    """
                    SELECT
                        p.pipeline_id,
                        p.pipeline_code,
                        p.pipeline_name,
                        pv.pipeline_version_id,
                        pv.version_no,
                        pv.status_code
                    FROM orch.pipeline_version AS pv
                    INNER JOIN orch.pipeline AS p
                        ON p.pipeline_id = pv.pipeline_id
                    WHERE pv.pipeline_version_id = %s;
                    """,
                    (pipeline_version_id,),
                )

                pipeline_row = cursor.fetchone()

                # A pipeline version without a pipeline is not executable
                # metadata.
                if pipeline_row is None:
                    raise LookupError(
                        "Pipeline version was not found: "
                        f"{pipeline_version_id}"
                    )

                (
                    pipeline_id,
                    pipeline_code,
                    pipeline_name,
                    resolved_pipeline_version_id,
                    version_no,
                    version_status,
                ) = pipeline_row

                # --------------------------------------------------------------
                # 2. Resolve pipeline task
                # --------------------------------------------------------------
                # A pipeline version can contain multiple tasks. For this
                # Customer POC we expect exactly one task.
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        task_code,
                        task_name,
                        task_type_code,
                        mapping_version_id,
                        sequence_no,
                        on_failure_code,
                        retry_policy_id,
                        timeout_seconds
                    FROM orch.pipeline_task
                    WHERE pipeline_version_id = %s
                    ORDER BY sequence_no, task_id;
                    """,
                    (pipeline_version_id,),
                )

                task_rows = cursor.fetchall()

                # The current POC expects one executable task.
                if not task_rows:
                    raise LookupError(
                        "No pipeline tasks were found for pipeline version "
                        f"{pipeline_version_id}."
                    )

                # Multiple tasks will be supported by the orchestration
                # engine later. For now, fail explicitly rather than silently
                # choosing the wrong task.
                if len(task_rows) != 1:
                    raise ValueError(
                        "Expected exactly one task for the Customer POC, "
                        f"but found {len(task_rows)}."
                    )

                task_row = task_rows[0]

                (
                    task_id,
                    task_code,
                    task_name,
                    task_type_code,
                    mapping_version_id,
                    sequence_no,
                    on_failure_code,
                    retry_policy_id,
                    timeout_seconds,
                ) = task_row

                # A task without a mapping cannot execute a metadata-driven
                # ingestion.
                if mapping_version_id is None:
                    raise LookupError(
                        f"Task {task_id} does not reference a mapping version."
                    )

                # Construct the runtime task object.
                runtime_task = RuntimeTask(
                    task_id=task_id,
                    task_code=task_code,
                    task_name=task_name,
                    task_type_code=task_type_code,
                    sequence_no=sequence_no,
                    on_failure_code=on_failure_code,
                    retry_policy_id=retry_policy_id,
                    timeout_seconds=timeout_seconds,
                    mapping_version_id=mapping_version_id,
                )

                # --------------------------------------------------------------
                # 3. Resolve mapping version
                # --------------------------------------------------------------
                # Use the exact deployed mapping_version column names discovered
                # during our schema inspection.
                cursor.execute(
                    """
                    SELECT
                        mapping_version_id,
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
                    (mapping_version_id,),
                )

                mapping_row = cursor.fetchone()

                if mapping_row is None:
                    raise LookupError(
                        "Mapping version was not found: "
                        f"{mapping_version_id}"
                    )

                (
                    resolved_mapping_version_id,
                    mapping_id,
                    mapping_version_no,
                    primary_source_dataset_id,
                    primary_source_schema_version_id,
                    target_dataset_id,
                    target_schema_version_id,
                    datatype_mapping_set_id,
                    load_type_code,
                    load_strategy_code,
                    mapping_status,
                ) = mapping_row

                # Construct the mapping runtime object.
                runtime_mapping = RuntimeMapping(
                    mapping_version_id=resolved_mapping_version_id,
                    mapping_id=mapping_id,
                    version_no=mapping_version_no,
                    primary_source_dataset_id=primary_source_dataset_id,
                    primary_source_schema_version_id=primary_source_schema_version_id,
                    target_dataset_id=target_dataset_id,
                    target_schema_version_id=target_schema_version_id,
                    datatype_mapping_set_id=datatype_mapping_set_id,
                    load_type_code=load_type_code,
                    load_strategy_code=load_strategy_code,
                    status_code=mapping_status,
                )

                # --------------------------------------------------------------
                # 4. Resolve load configuration
                # --------------------------------------------------------------
                # This contains batch and preparation behavior for the load.
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
                      AND is_active = TRUE
                    ORDER BY load_config_id DESC
                    LIMIT 1;
                    """,
                    (mapping_version_id,),
                )

                load_row = cursor.fetchone()

                if load_row is None:
                    raise LookupError(
                        "Active load configuration was not found for "
                        f"mapping version {mapping_version_id}."
                    )

                (
                    load_config_id,
                    load_mapping_version_id,
                    config_load_type,
                    batch_size,
                    truncate_before_load,
                    is_active,
                ) = load_row

                # Validate the batch size before passing it to the execution
                # engine.
                if batch_size <= 0:
                    raise ValueError(
                        f"Invalid batch size: {batch_size}"
                    )

                # Construct the generic load configuration object.
                runtime_load_config = RuntimeLoadConfig(
                    load_config_id=load_config_id,
                    mapping_version_id=load_mapping_version_id,
                    load_type_code=config_load_type,
                    batch_size=batch_size,
                    truncate_before_load=truncate_before_load,
                    is_active=is_active,
                )

                # --------------------------------------------------------------
                # 5. Resolve target load configuration
                # --------------------------------------------------------------
                # Use the exact deployed column names from
                # ingest.target_load_config.
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
                    WHERE mapping_version_id = %s;
                    """,
                    (mapping_version_id,),
                )

                target_row = cursor.fetchone()

                if target_row is None:
                    raise LookupError(
                        "Target load configuration was not found for "
                        f"mapping version {mapping_version_id}."
                    )

                (
                    target_mapping_version_id,
                    load_method_code,
                    commit_size,
                    auto_create_target,
                    alter_target_policy_code,
                    transaction_mode_code,
                    write_timeout_seconds,
                    target_prepare_action_code,
                    target_schema_policy_code,
                    constraint_apply_policy_code,
                    index_apply_policy_code,
                ) = target_row

                # The target timeout must be positive.
                if write_timeout_seconds <= 0:
                    raise ValueError(
                        "Target write timeout must be greater than zero."
                    )

                # Construct the target runtime configuration object.
                runtime_target_config = RuntimeTargetConfig(
                    mapping_version_id=target_mapping_version_id,
                    load_method_code=load_method_code,
                    commit_size=commit_size,
                    auto_create_target=auto_create_target,
                    alter_target_policy_code=alter_target_policy_code,
                    transaction_mode_code=transaction_mode_code,
                    write_timeout_seconds=write_timeout_seconds,
                    target_prepare_action_code=target_prepare_action_code,
                    target_schema_policy_code=target_schema_policy_code,
                    constraint_apply_policy_code=constraint_apply_policy_code,
                    index_apply_policy_code=index_apply_policy_code,
                )

        # ----------------------------------------------------------------------
        # 6. Build the final execution plan
        # ----------------------------------------------------------------------
        # At this point all required metadata has been resolved and validated.
        return RuntimeExecutionPlan(
            pipeline_id=pipeline_id,
            pipeline_version_id=resolved_pipeline_version_id,
            pipeline_version_no=version_no,
            pipeline_version_status=version_status,
            pipeline_code=pipeline_code,
            pipeline_name=pipeline_name,
            task=runtime_task,
            mapping=runtime_mapping,
            load_config=runtime_load_config,
            target_config=runtime_target_config,
        )