from app.runtime.models import (
    RuntimeExecutionPlan,
    RuntimeLoadConfig,
    RuntimeMapping,
    RuntimeTargetConfig,
    RuntimeTask,
)
from app.db.metastore import get_metastore_connection


class RuntimeMetadataResolver:
    """Resolve runtime execution plans from pipeline metadata."""

    def resolve(self, pipeline_version_id: int) -> RuntimeExecutionPlan:
        """
        Backward-compatible API for pipelines containing one task.
        """
        plans = self.resolve_all(pipeline_version_id)

        if len(plans) != 1:
            raise ValueError(
                "Expected exactly one task when using resolve(); "
                f"found {len(plans)}. Use resolve_all() for multi-task pipelines."
            )

        return plans[0]

    def resolve_all(
        self,
        pipeline_version_id: int,
    ) -> list[RuntimeExecutionPlan]:
        """Resolve one execution plan for every task in sequence."""

        if pipeline_version_id <= 0:
            raise ValueError(
                "pipeline_version_id must be greater than zero."
            )

        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:

                # 1. Resolve the pipeline version.
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

                # 2. Resolve all tasks in execution order.
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

                if not task_rows:
                    raise LookupError(
                        "No pipeline tasks were found for pipeline version "
                        f"{pipeline_version_id}."
                    )

                # 3. Resolve an independent plan for every task.
                plans = []

                for task_row in task_rows:
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

                    if mapping_version_id is None:
                        raise LookupError(
                            f"Task {task_id} does not reference "
                            "a mapping version."
                        )

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

                    # 4. Resolve the task's mapping version.
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

                    runtime_mapping = RuntimeMapping(
                        mapping_version_id=resolved_mapping_version_id,
                        mapping_id=mapping_id,
                        version_no=mapping_version_no,
                        primary_source_dataset_id=primary_source_dataset_id,
                        primary_source_schema_version_id=(
                            primary_source_schema_version_id
                        ),
                        target_dataset_id=target_dataset_id,
                        target_schema_version_id=target_schema_version_id,
                        datatype_mapping_set_id=datatype_mapping_set_id,
                        load_type_code=load_type_code,
                        load_strategy_code=load_strategy_code,
                        status_code=mapping_status,
                    )

                    # 5. Resolve the active load configuration.
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

                    if batch_size <= 0:
                        raise ValueError(
                            f"Invalid batch size: {batch_size}"
                        )

                    runtime_load_config = RuntimeLoadConfig(
                        load_config_id=load_config_id,
                        mapping_version_id=load_mapping_version_id,
                        load_type_code=config_load_type,
                        batch_size=batch_size,
                        truncate_before_load=truncate_before_load,
                        is_active=is_active,
                    )

                    # 6. Resolve target-specific load configuration.
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

                    if write_timeout_seconds <= 0:
                        raise ValueError(
                            "Target write timeout must be greater than zero."
                        )

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

                    # 7. Build this task's independent execution plan.
                    plans.append(
                        RuntimeExecutionPlan(
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
                    )

                return plans