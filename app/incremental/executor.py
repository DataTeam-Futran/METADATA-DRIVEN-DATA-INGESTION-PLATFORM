from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.incremental.models import (
    IncrementalExecutionResult,
    IncrementalTablePlan,
)
from app.incremental.repository import IncrementalRepository
from app.incremental.schema import (
    SchemaValidationError,
    add_missing_target_columns,
    build_incremental_query,
    compare_schemas,
    discover_columns,
)
from app.runtime.connection_resolver import RuntimeConnectionResolver


class IncrementalExecutor:
    def __init__(self, repository: IncrementalRepository | None = None) -> None:
        self.repository = repository or IncrementalRepository()

    def execute(
        self,
        tenant_id: int,
        system_id: int,
        environment_id: int,
        source_connection_id: int,
        load_type: str = "INCREMENTAL",
        load_strategy: str = "APPEND",
    ) -> IncrementalExecutionResult:
        self._validate_request(
            tenant_id,
            system_id,
            environment_id,
            source_connection_id,
            load_type,
            load_strategy,
        )
        profile = self.repository.get_connection_scope(source_connection_id)
        expected_profile = (
            tenant_id,
            system_id,
            environment_id,
            3,
            1,
            source_connection_id,
            "SOURCE",
            "ACTIVE",
        )
        if profile != expected_profile:
            raise ValueError(
                "Source profile does not match the requested tenant, system, "
                "environment, connector version, credential, role, and active status."
            )

        plans = self.repository.resolve_table_plans(
            tenant_id,
            environment_id,
            source_connection_id,
            load_type,
            load_strategy,
        )
        target_connection_ids = {
            plan.target_object.connection_id for plan in plans
        }
        if len(target_connection_ids) != 1:
            raise ValueError(
                "One atomic execution must use a single target connection."
            )
        target_profile = self.repository.get_connection_scope(
            next(iter(target_connection_ids))
        )
        if (
            target_profile[0:3] != (tenant_id, system_id, environment_id)
            or target_profile[6] not in ("TARGET", "BOTH")
            or target_profile[7] != "ACTIVE"
        ):
            raise ValueError(
                "Resolved target connection is inactive or outside the requested scope."
            )

        resolver = RuntimeConnectionResolver()
        source_connector = resolver.resolve(source_connection_id)
        target_connector = resolver.resolve(next(iter(target_connection_ids)))
        execution_id = uuid4()
        execution_watermark = datetime.now(timezone.utc)
        execution_started = False
        target_transaction_started = False
        rows_read = 0
        rows_inserted = 0
        rows_skipped = 0
        results: list[tuple[IncrementalTablePlan, int, int, int]] = []
        failed_plan: IncrementalTablePlan | None = None
        failed_step = "CONNECT_SOURCE"

        try:
            source_connector.connect()
            with source_connector._require_connection().cursor() as cursor:
                cursor.execute("SELECT CURRENT_TIMESTAMP;")
                execution_watermark = cursor.fetchone()[0]
            if execution_watermark.tzinfo is None:
                execution_watermark = execution_watermark.replace(
                    tzinfo=timezone.utc
                )

            self.repository.start_execution(
                execution_id,
                tenant_id,
                system_id,
                environment_id,
                source_connection_id,
                execution_watermark,
            )
            execution_started = True

            with self.repository.mapping_locks(plans):
                target_connector.connect()
                target_connector.begin_transaction()
                target_transaction_started = True

                for plan in plans:
                    failed_plan = plan
                    failed_step = "DISCOVER_SCHEMA"
                    self.repository.start_table_execution(
                        execution_id,
                        tenant_id,
                        plan,
                        execution_watermark,
                    )
                    source_columns = discover_columns(
                        source_connector,
                        plan.source_object,
                    )
                    target_columns = discover_columns(
                        target_connector,
                        plan.target_object,
                    )
                    self.repository.persist_schema_metadata(
                        tenant_id,
                        plan.source_object.dataset_id,
                        plan.source_object.dataset_binding_id,
                        source_columns,
                        plan.watermark_column,
                    )
                    target_schema_changes = 0

                    failed_step = "VALIDATE_SCHEMA"
                    if plan.schema_strategy == "ADD_MISSING_COLUMNS":
                        source_names = {column.name for column in source_columns}
                        target_names = {column.name for column in target_columns}
                        if source_names - target_names:
                            target_schema_changes = add_missing_target_columns(
                                target_connector,
                                plan.target_object,
                                source_columns,
                                target_columns,
                            )
                            target_columns = discover_columns(
                                target_connector,
                                plan.target_object,
                            )
                    elif plan.schema_strategy != "STRICT":
                        raise ValueError(
                            f"Unsupported schema strategy {plan.schema_strategy!r}."
                        )

                    differences = compare_schemas(
                        source_columns,
                        target_columns,
                        plan.watermark_column,
                        require_primary_key=(plan.duplicate_strategy != "ALLOW"),
                    )
                    if differences:
                        raise SchemaValidationError("; ".join(differences))

                    source_names = tuple(column.name for column in source_columns)
                    target_names = tuple(column.name for column in source_columns)
                    source_primary_keys = tuple(
                        column.name
                        for column in source_columns
                        if column.is_primary_key
                    )
                    target_primary_keys = tuple(
                        column.name
                        for column in target_columns
                        if column.is_primary_key
                    )
                    if plan.duplicate_strategy == "SKIP" and (
                        source_primary_keys != target_primary_keys
                    ):
                        raise SchemaValidationError(
                            "SKIP requires matching source and target primary keys."
                        )
                    watermark_metadata = next(
                        column
                        for column in source_columns
                        if column.name == plan.watermark_column
                    )
                    if "timestamp" not in watermark_metadata.data_type.lower():
                        raise SchemaValidationError(
                            f"Watermark {plan.watermark_column!r} must be a timestamp column; "
                            f"found {watermark_metadata.data_type!r}."
                        )
                    previous_watermark = self._resolve_previous_watermark(plan)

                    failed_step = "READ_AND_APPEND"
                    source_query = build_incremental_query(
                        plan.source_object,
                        source_names,
                        plan.watermark_column,
                    )
                    table_source_count = 0
                    table_inserted_count = 0
                    for batch in source_connector.read_batches(
                        source_query,
                        batch_size=plan.batch_size,
                        parameters=(previous_watermark, execution_watermark),
                    ):
                        table_source_count += len(batch)
                        table_inserted_count += target_connector.write_batch(
                            target_schema=plan.target_object.schema_name or "",
                            target_table=plan.target_object.object_name,
                            column_names=list(target_names),
                            rows=batch,
                            duplicate_strategy=plan.duplicate_strategy,
                            primary_key_columns=list(source_primary_keys),
                        )

                    table_skipped = table_source_count - table_inserted_count
                    if table_skipped < 0:
                        raise RuntimeError(
                            "Target inserted more rows than the source returned."
                        )
                    rows_read += table_source_count
                    rows_inserted += table_inserted_count
                    rows_skipped += table_skipped
                    self.repository.persist_schema_metadata(
                        tenant_id,
                        plan.target_object.dataset_id,
                        plan.target_object.dataset_binding_id,
                        target_columns,
                        plan.watermark_column,
                    )
                    results.append(
                        (
                            IncrementalTablePlan(
                                mapping_version_id=plan.mapping_version_id,
                                source_object=plan.source_object,
                                target_object=plan.target_object,
                                source_columns=source_names,
                                target_columns=target_names,
                                watermark_column=plan.watermark_column,
                                primary_key_columns=source_primary_keys,
                                previous_watermark=previous_watermark,
                                initial_watermark=plan.initial_watermark,
                                batch_size=plan.batch_size,
                                schema_strategy=plan.schema_strategy,
                                duplicate_strategy=plan.duplicate_strategy,
                            ),
                            table_source_count,
                            table_inserted_count,
                            target_schema_changes,
                        )
                    )

                failed_step = "COMMIT_TARGET"
                target_connector.commit()
                target_transaction_started = False

                failed_step = "COMMIT_WATERMARKS"
                self.repository.finalize_success(
                    execution_id,
                    tenant_id,
                    execution_watermark,
                    results,
                )
                return IncrementalExecutionResult(
                    execution_id=str(execution_id),
                    status="SUCCESS",
                    tables_processed=len(results),
                    rows_read=rows_read,
                    rows_inserted=rows_inserted,
                    rows_skipped=rows_skipped,
                    execution_watermark=execution_watermark,
                    watermark_updated=True,
                )
        except Exception as error:
            if target_transaction_started:
                try:
                    target_connector.rollback()
                except Exception:
                    pass
            if execution_started:
                self.repository.finalize_failure(
                    execution_id,
                    rows_read,
                    rows_inserted,
                    rows_skipped,
                    failed_plan.source_object.object_name if failed_plan else None,
                    failed_step,
                    error,
                )
            raise
        finally:
            for connector in (target_connector, source_connector):
                try:
                    connector.close()
                except Exception:
                    pass

    @staticmethod
    def _resolve_previous_watermark(plan: IncrementalTablePlan) -> datetime:
        raw_value = plan.previous_watermark or plan.initial_watermark
        if raw_value is None or not str(raw_value).strip():
            raise ValueError(
                "No current watermark or configured initial watermark exists "
                f"for mapping version {plan.mapping_version_id}."
            )
        if isinstance(raw_value, datetime):
            value = raw_value
        else:
            value = datetime.fromisoformat(
                str(raw_value).strip().replace("Z", "+00:00")
            )
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _validate_request(
        tenant_id: int,
        system_id: int,
        environment_id: int,
        source_connection_id: int,
        load_type: str,
        load_strategy: str,
    ) -> None:
        if min(tenant_id, system_id, environment_id, source_connection_id) <= 0:
            raise ValueError("Tenant, system, environment, and connection IDs must be positive.")
        if load_type.upper() != "INCREMENTAL":
            raise ValueError("Only INCREMENTAL load type is supported.")
        if load_strategy.upper() != "APPEND":
            raise ValueError("Only APPEND load strategy is supported.")