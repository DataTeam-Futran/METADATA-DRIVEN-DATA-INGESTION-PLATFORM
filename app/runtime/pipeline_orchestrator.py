
"""
Metadata-Driven Pipeline Orchestrator
=====================================

Responsibilities:
- Resolve tasks configured for a pipeline version.
- Select tasks by task code, source table, or target table.
- Resolve physical object metadata before creating connectors.
- Resolve runtime context and field mappings.
- Validate source and target objects before execution.
- Prevent execution if any validation result fails.
- Execute selected tasks using the existing FullLoadExecutor.
- Report task-level and pipeline-level execution results.

The orchestrator contains no hardcoded physical table names.
"""

import sys
from dataclasses import dataclass

from app.runtime.context_resolver import RuntimeExecutionContextResolver
from app.runtime.field_mapping_resolver import RuntimeFieldMappingResolver
from app.runtime.full_load_executor import FullLoadExecutor
from app.runtime.metadata_resolver import RuntimeMetadataResolver
from app.runtime.pre_execution_validator import PreExecutionValidator
from app.runtime.run_tracker import RuntimeRunTracker
from app.runtime.selective_table_full_load_executor import _format_table


@dataclass(frozen=True)
class TaskExecutionResult:
    """Summary of one successfully executed pipeline task."""

    task_id: int
    task_code: str
    task_name: str
    mapping_version_id: int
    rows_written: int


class PipelineOrchestrator:
    """Execute all or selected tasks from metadata."""

    def __init__(
        self,
        metadata_resolver: RuntimeMetadataResolver | None = None,
        context_resolver: RuntimeExecutionContextResolver | None = None,
        field_mapping_resolver: RuntimeFieldMappingResolver | None = None,
        pre_execution_validator: PreExecutionValidator | None = None,
        run_tracker: RuntimeRunTracker | None = None,
    ) -> None:
        self._metadata_resolver = (
            metadata_resolver or RuntimeMetadataResolver()
        )
        self._context_resolver = (
            context_resolver or RuntimeExecutionContextResolver()
        )
        self._field_mapping_resolver = (
            field_mapping_resolver or RuntimeFieldMappingResolver()
        )
        self._pre_execution_validator = (
            pre_execution_validator or PreExecutionValidator()
        )
        self._run_tracker = run_tracker or RuntimeRunTracker()

    @staticmethod
    def _normalize_names(
        values: list[str] | None,
        parameter_name: str,
    ) -> set[str] | None:
        """Normalize optional selection values."""

        if values is None:
            return None

        names = {
            value.strip().casefold()
            for value in values
            if isinstance(value, str) and value.strip()
        }

        if not names:
            raise ValueError(
                f"{parameter_name} must contain at least one "
                "non-empty name when supplied."
            )

        return names

    @staticmethod
    def _table_name_matches(
        requested_names: set[str],
        catalog_name: str | None,
        schema_name: str | None,
        object_name: str,
    ) -> bool:
        """Match by table, schema.table, or catalog.schema.table."""

        table = object_name.strip().casefold()
        candidates = {table}

        if schema_name and schema_name.strip():
            schema = schema_name.strip().casefold()
            candidates.add(f"{schema}.{table}")

        if (
            catalog_name
            and catalog_name.strip()
            and schema_name
            and schema_name.strip()
        ):
            catalog = catalog_name.strip().casefold()
            schema = schema_name.strip().casefold()
            candidates.add(f"{catalog}.{schema}.{table}")

        normalized_requested = {
            name.strip().casefold()
            for name in requested_names
            if name.strip()
        }

        return bool(normalized_requested & candidates)

    def execute_pipeline(
        self,
        pipeline_version_id: int,
        tenant_id: int,
        environment_id: int,
        selected_task_codes: list[str] | None = None,
        selected_source_tables: list[str] | None = None,
        selected_target_tables: list[str] | None = None,
    ) -> list[TaskExecutionResult]:
        """Execute selected tasks and persist pipeline/task run status."""

        if pipeline_version_id <= 0:
            raise ValueError(
                "pipeline_version_id must be greater than zero."
            )

        if tenant_id <= 0:
            raise ValueError("tenant_id must be greater than zero.")

        if environment_id <= 0:
            raise ValueError("environment_id must be greater than zero.")

        requested_codes = None

        if selected_task_codes is not None:
            requested_codes = {
                code.strip().casefold()
                for code in selected_task_codes
                if isinstance(code, str) and code.strip()
            }

            if not requested_codes:
                raise ValueError(
                    "selected_task_codes must contain at least one "
                    "non-empty task code when supplied."
                )

        requested_sources = self._normalize_names(
            selected_source_tables,
            "selected_source_tables",
        )

        requested_targets = self._normalize_names(
            selected_target_tables,
            "selected_target_tables",
        )

        selection_description = (
            "all configured tasks"
            if (
                requested_codes is None
                and requested_sources is None
                and requested_targets is None
            )
            else "selected tasks"
        )

        plans = self._metadata_resolver.resolve_all(
            pipeline_version_id=pipeline_version_id
        )

        if not plans:
            raise LookupError(
                f"No tasks found for pipeline version "
                f"{pipeline_version_id}."
            )

        unpublished_plans = [
            plan
            for plan in plans
            if plan.pipeline_version_status.strip().upper()
            != "PUBLISHED"
        ]
        if unpublished_plans:
            raise PermissionError(
                "Pipeline execution is blocked because the pipeline "
                f"version is not PUBLISHED (current status: "
                f"{unpublished_plans[0].pipeline_version_status}). "
                "Complete the existing approval and publish workflow first."
            )

        inactive_mappings = [
            plan
            for plan in plans
            if plan.mapping.status_code.strip().upper() != "ACTIVE"
        ]
        if inactive_mappings:
            statuses = sorted(
                {
                    plan.mapping.status_code
                    for plan in inactive_mappings
                }
            )
            raise PermissionError(
                "Pipeline execution is blocked because one or more "
                "mapping versions are not ACTIVE "
                f"(statuses: {statuses}). Complete the existing mapping "
                "approval workflow first."
            )

        available_codes = {
            plan.task.task_code.strip().casefold()
            for plan in plans
        }

        if requested_codes is not None:
            unknown_codes = requested_codes - available_codes

            if unknown_codes:
                raise ValueError(
                    "Requested task code(s) were not found in pipeline "
                    f"metadata: {sorted(unknown_codes)}"
                )

        run_id, project_id, batch_id = (
            self._run_tracker.start_pipeline(
                pipeline_version_id=pipeline_version_id,
                tenant_id=tenant_id,
                environment_id=environment_id,
            )
        )

        results: list[TaskExecutionResult] = []
        total_rows_written = 0
        pipeline_status = "FAILED"

        print("=" * 80)
        print("METADATA-DRIVEN PIPELINE EXECUTION")
        print("=" * 80)
        print(f"Pipeline version : {pipeline_version_id}")
        print(f"Pipeline run ID  : {run_id}")
        print(f"Batch ID         : {batch_id}")
        print(f"Selection mode   : {selection_description}")
        print(f"Configured tasks : {len(plans)}")
        print()

        try:
            for plan in plans:
                task = plan.task
                mapping = plan.mapping

                # Filter by task code before resolving dataset bindings.
                if (
                    requested_codes is not None
                    and task.task_code.strip().casefold()
                    not in requested_codes
                ):
                    continue

                # Resolve physical object metadata only.
                # This does not create source or target connectors.
                source, target = (
                    self._context_resolver.resolve_objects_for_plan(
                        execution_plan=plan,
                        tenant_id=tenant_id,
                        environment_id=environment_id,
                    )
                )

                # Apply source-table filter before connector resolution.
                if requested_sources is not None:
                    if not self._table_name_matches(
                        requested_sources,
                        source.catalog_name,
                        source.schema_name,
                        source.object_name,
                    ):
                        continue

                # Apply target-table filter before connector resolution.
                if requested_targets is not None:
                    if not self._table_name_matches(
                        requested_targets,
                        target.catalog_name,
                        target.schema_name,
                        target.object_name,
                    ):
                        continue

                task_run_id = None
                task_started = None
                rows_written = 0

                print("-" * 80)
                print(f"Task          : {task.task_name}")
                print(f"Task code     : {task.task_code}")
                print(f"Task ID       : {task.task_id}")
                print(f"Mapping ID    : {mapping.mapping_version_id}")
                print(
                    "Source object : "
                    f"{source.catalog_name}.{source.schema_name}."
                    f"{source.object_name}"
                )
                print(
                    "Target object : "
                    f"{target.catalog_name}.{target.schema_name}."
                    f"{target.object_name}"
                )

                try:
                    # Start tracking before connector resolution.
                    task_run_id, task_started = (
                        self._run_tracker.start_task(
                            run_id=run_id,
                            tenant_id=tenant_id,
                            project_id=project_id,
                            task_id=task.task_id,
                            mapping_version_id=mapping.mapping_version_id,
                        )
                    )

                    # Resolve connectors only after the task matches filters.
                    context = self._context_resolver.resolve_for_plan(
                        execution_plan=plan,
                        tenant_id=tenant_id,
                        environment_id=environment_id,
                    )

                    field_mappings = (
                        self._field_mapping_resolver.resolve(
                            mapping_version_id=mapping.mapping_version_id,
                            tenant_id=tenant_id,
                        )
                    )

                    print()
                    print("SOURCE-TO-TARGET COLUMN MAPPING")
                    print("-" * 80)
                    print(
                        f"{'Source Column':<32} "
                        f"{'Target Column':<32} "
                        f"{'Type':<12} "
                        "Metadata IDs"
                    )
                    for field_mapping in field_mappings:
                        print(
                            f"{field_mapping.source_field_name:<32} "
                            f"{field_mapping.target_field_name:<32} "
                            f"{field_mapping.mapping_type_code:<12} "
                            f"{field_mapping.source_field_id} -> "
                            f"{field_mapping.target_field_id}"
                        )

                    print()
                    print("PRE-EXECUTION VALIDATION")
                    print("-" * 80)

                    validation_results = (
                        self._pre_execution_validator.validate(
                            context=context,
                            field_mappings=field_mappings,
                        )
                    )

                    validation_rows = [
                        [
                            source.schema_name + "." + source.object_name,
                            validation_result.check_name,
                            "PASSED" if validation_result.passed else "FAILED",
                            validation_result.message,
                        ]
                        for validation_result in validation_results
                    ]
                    for line in _format_table(
                        ["Table", "Validation Check", "Status", "Details"],
                        validation_rows,
                    ):
                        print(line)

                    # SAFETY GATE:
                    # Never invoke the executor when any check fails.
                    failed_checks = [
                        result
                        for result in validation_results
                        if not result.passed
                    ]

                    if failed_checks:
                        failure_details = "; ".join(
                            f"{result.check_name}: {result.message}"
                            for result in failed_checks
                        )

                        raise RuntimeError(
                            "Pre-execution validation failed. "
                            "The executor was not started. Details: "
                            f"{failure_details}"
                        )

                    # Execution starts only after all checks pass.
                    executor = FullLoadExecutor()

                    rows_written = executor.execute(
                        context=context,
                        field_mappings=field_mappings,
                    )

                    # Persist task success before adding it to results.
                    self._run_tracker.finish_task(
                        task_run_id=task_run_id,
                        started=task_started,
                        status_code="SUCCESS",
                        rows_written=rows_written,
                    )

                    results.append(
                        TaskExecutionResult(
                            task_id=task.task_id,
                            task_code=task.task_code,
                            task_name=task.task_name,
                            mapping_version_id=mapping.mapping_version_id,
                            rows_written=rows_written,
                        )
                    )

                    total_rows_written += rows_written

                    print(f"Rows written  : {rows_written}")
                    print("Task result   : SUCCESS")

                except Exception as exc:
                    print("Task result   : FAILED")
                    print(f"Failure reason: {exc}")

                    # Do not replace the original task exception with
                    # a secondary tracking failure.
                    if (
                        task_run_id is not None
                        and task_started is not None
                    ):
                        try:
                            self._run_tracker.finish_task(
                                task_run_id=task_run_id,
                                started=task_started,
                                status_code="FAILED",
                                rows_written=0,
                            )
                        except Exception as tracking_exc:
                            print(
                                "WARNING: Could not persist failed task "
                                f"status: {tracking_exc}"
                            )

                    # Preserve existing STOP behavior: fail the pipeline
                    # immediately when a task fails.
                    raise

            if not results:
                raise LookupError(
                    "No configured tasks matched the requested selection. "
                    "Check the physical table names and task filters."
                )

            pipeline_status = "SUCCESS"

        finally:
            original_exception_active = sys.exc_info()[0] is not None

            try:
                self._run_tracker.finish_pipeline(
                    run_id=run_id,
                    status_code=pipeline_status,
                )
            except Exception as tracking_exc:
                if original_exception_active:
                    print(
                        "WARNING: Could not persist final pipeline status "
                        f"for run {run_id}: {tracking_exc}"
                    )
                else:
                    raise RuntimeError(
                        f"Pipeline execution finished with status "
                        f"{pipeline_status}, but final status tracking "
                        f"failed for run {run_id}."
                    ) from tracking_exc

        print()
        print("=" * 80)
        print("PIPELINE EXECUTION COMPLETED")
        print(f"Pipeline run ID    : {run_id}")
        print(f"Pipeline status    : {pipeline_status}")
        print(f"Successful tasks   : {len(results)}")
        print(f"Total rows written : {total_rows_written}")
        print("=" * 80)

        return results
