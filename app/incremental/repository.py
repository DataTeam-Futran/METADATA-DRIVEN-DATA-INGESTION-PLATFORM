from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.metastore import get_metastore_connection
from app.incremental.models import ColumnMetadata, IncrementalTablePlan
from app.runtime.object_resolver import RuntimeObjectResolver


class IncrementalRepository:
    """Persistence for incremental config, checkpoints, discovery, and runs."""

    def resolve_table_plans(
        self,
        tenant_id: int,
        environment_id: int,
        source_connection_id: int,
        load_type: str,
        load_strategy: str,
    ) -> list[IncrementalTablePlan]:
        query = """
            SELECT
                mv.mapping_version_id,
                mv.primary_source_dataset_id,
                mv.target_dataset_id,
                source_binding.connection_id,
                source_binding.dataset_binding_id,
                target_binding.connection_id,
                target_binding.dataset_binding_id,
                source_binding.catalog_name,
                source_binding.schema_name,
                source_binding.object_name,
                target_binding.catalog_name,
                target_binding.schema_name,
                target_binding.object_name,
                watermark_field.field_name,
                ic.initial_watermark_value,
                state.current_value,
                lc.batch_size,
                rc.schema_strategy,
                rc.duplicate_strategy,
                mv.load_type_code,
                mv.load_strategy_code
            FROM map.mapping_version AS mv
            INNER JOIN map.mapping AS m
              ON m.mapping_id = mv.mapping_id
             AND m.tenant_id = mv.tenant_id
            INNER JOIN catalog.dataset_binding AS source_binding
              ON source_binding.dataset_id = mv.primary_source_dataset_id
             AND source_binding.tenant_id = mv.tenant_id
             AND source_binding.environment_id = %s
             AND source_binding.status_code = 'ACTIVE'
            INNER JOIN catalog.dataset_binding AS target_binding
              ON target_binding.dataset_id = mv.target_dataset_id
             AND target_binding.tenant_id = mv.tenant_id
             AND target_binding.environment_id = %s
             AND target_binding.status_code = 'ACTIVE'
            INNER JOIN ingest.incremental_config AS ic
              ON ic.mapping_version_id = mv.mapping_version_id
             AND ic.tenant_id = mv.tenant_id
            INNER JOIN ingest.load_config AS lc
              ON lc.mapping_version_id = mv.mapping_version_id
             AND lc.load_type_code = 'INCREMENTAL'
             AND lc.is_active
            INNER JOIN ingest.incremental_runtime_config AS rc
              ON rc.mapping_version_id = mv.mapping_version_id
             AND rc.tenant_id = mv.tenant_id
             AND rc.is_active
            INNER JOIN catalog.dataset_field AS watermark_field
              ON watermark_field.field_id = ic.watermark_field_id
            LEFT JOIN ingest.watermark_state AS state
              ON state.mapping_version_id = mv.mapping_version_id
             AND state.tenant_id = mv.tenant_id
            WHERE mv.tenant_id = %s
              AND source_binding.connection_id = %s
              AND mv.load_type_code = %s
              AND mv.load_strategy_code = %s
              AND mv.status_code IN ('ACTIVE', 'PUBLISHED')
              AND m.status_code IN ('ACTIVE', 'PUBLISHED')
            ORDER BY mv.mapping_version_id;
        """
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        environment_id,
                        environment_id,
                        tenant_id,
                        source_connection_id,
                        load_type.upper(),
                        load_strategy.upper(),
                    ),
                )
                rows = cursor.fetchall()

        object_resolver = RuntimeObjectResolver()
        plans = []
        for row in rows:
            (
                mapping_version_id,
                source_dataset_id,
                target_dataset_id,
                source_connection_id,
                source_binding_id,
                target_connection_id,
                target_binding_id,
                source_catalog,
                source_schema,
                source_table,
                target_catalog,
                target_schema,
                target_table,
                watermark_column,
                initial_watermark,
                previous_watermark,
                batch_size,
                schema_strategy,
                duplicate_strategy,
                resolved_load_type,
                resolved_load_strategy,
            ) = row
            if source_connection_id <= 0 or target_connection_id <= 0:
                raise ValueError("Mapping contains an invalid connection binding.")
            if resolved_load_type != load_type.upper() or resolved_load_strategy != load_strategy.upper():
                raise ValueError("Mapping load configuration does not match request.")
            source_object = object_resolver.resolve(
                source_dataset_id, tenant_id, environment_id
            )
            target_object = object_resolver.resolve(
                target_dataset_id, tenant_id, environment_id
            )
            if (
                source_object.dataset_binding_id != source_binding_id
                or target_object.dataset_binding_id != target_binding_id
                or source_object.catalog_name != source_catalog
                or target_object.catalog_name != target_catalog
                or source_object.schema_name != source_schema
                or target_object.schema_name != target_schema
                or source_object.object_name != source_table
                or target_object.object_name != target_table
            ):
                raise RuntimeError("Dataset binding changed while resolving the run plan.")
            plans.append(
                IncrementalTablePlan(
                    mapping_version_id=mapping_version_id,
                    source_object=source_object,
                    target_object=target_object,
                    source_columns=(),
                    target_columns=(),
                    watermark_column=watermark_column,
                    primary_key_columns=(),
                    previous_watermark=previous_watermark,
                    initial_watermark=initial_watermark,
                    batch_size=batch_size,
                    schema_strategy=schema_strategy,
                    duplicate_strategy=duplicate_strategy,
                )
            )
        if not plans:
            raise LookupError(
                "No active INCREMENTAL/APPEND mapping with source and target "
                "dataset bindings was found for this connection."
            )
        return plans

    def get_connection_scope(
        self,
        connection_id: int,
    ) -> tuple[int, int, int, int, int, int, str, str]:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        tenant_id, system_id, environment_id,
                        connector_version_id, credential_id,
                        connection_id, connection_role_code, status_code
                    FROM conn.connection_profile
                    WHERE connection_id = %s;
                    """,
                    (connection_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Connection {connection_id} does not exist.")
        return row

    @contextmanager
    def mapping_locks(self, plans: list[IncrementalTablePlan]):
        """Hold session advisory locks to prevent overlapping table runs."""
        with get_metastore_connection() as connection:
            acquired: list[int] = []
            try:
                with connection.cursor() as cursor:
                    for mapping_version_id in sorted(
                        plan.mapping_version_id for plan in plans
                    ):
                        cursor.execute(
                            "SELECT pg_try_advisory_lock(%s, hashtext(%s));",
                            (1835264877, str(mapping_version_id)),
                        )
                        if not cursor.fetchone()[0]:
                            raise RuntimeError(
                                "An incremental run is already active for "
                                f"mapping version {mapping_version_id}."
                            )
                        acquired.append(mapping_version_id)
                yield
            finally:
                if acquired:
                    with connection.cursor() as cursor:
                        for mapping_version_id in reversed(acquired):
                            cursor.execute(
                                "SELECT pg_advisory_unlock(%s, hashtext(%s));",
                                (1835264877, str(mapping_version_id)),
                            )

    def start_execution(
        self,
        execution_id: UUID,
        tenant_id: int,
        system_id: int,
        environment_id: int,
        source_connection_id: int,
        execution_watermark: datetime,
    ) -> None:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ingest.incremental_execution (
                        execution_id, tenant_id, system_id, environment_id,
                        source_connection_id, load_type_code,
                        load_strategy_code, execution_watermark, status_code
                    ) VALUES (%s,%s,%s,%s,%s,'INCREMENTAL','APPEND',%s,'RUNNING');
                    """,
                    (
                        execution_id,
                        tenant_id,
                        system_id,
                        environment_id,
                        source_connection_id,
                        execution_watermark,
                    ),
                )
            connection.commit()

    def start_table_execution(
        self,
        execution_id: UUID,
        tenant_id: int,
        plan: IncrementalTablePlan,
        execution_watermark: datetime,
    ) -> None:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO ingest.incremental_execution_table (
                        execution_id, mapping_version_id, tenant_id,
                        source_dataset_id, target_dataset_id, source_table,
                        target_table, previous_watermark,
                        execution_watermark, status_code
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'RUNNING');
                    """,
                    (
                        execution_id,
                        plan.mapping_version_id,
                        tenant_id,
                        plan.source_object.dataset_id,
                        plan.target_object.dataset_id,
                        plan.source_object.object_name,
                        plan.target_object.object_name,
                        str(plan.previous_watermark or plan.initial_watermark or ""),
                        execution_watermark,
                    ),
                )
            connection.commit()

    def update_table_execution(
        self,
        execution_id: UUID,
        mapping_version_id: int,
        source_count: int,
        inserted_count: int,
        schema_change_count: int,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingest.incremental_execution_table
                    SET source_count=%s, inserted_count=%s,
                        duplicate_count=%s, schema_change_count=%s,
                        status_code=%s, error_message=%s, ended_at=CURRENT_TIMESTAMP
                    WHERE execution_id=%s AND mapping_version_id=%s;
                    """,
                    (
                        source_count,
                        inserted_count,
                        max(source_count - inserted_count, 0),
                        schema_change_count,
                        status,
                        error_message,
                        execution_id,
                        mapping_version_id,
                    ),
                )
            connection.commit()

    def finish_execution(
        self,
        execution_id: UUID,
        status: str,
        rows_read: int,
        rows_inserted: int,
        rows_skipped: int,
        failed_table: str | None = None,
        failed_step: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingest.incremental_execution
                    SET status_code=%s, ended_at=CURRENT_TIMESTAMP,
                        rows_read=%s, rows_inserted=%s, rows_skipped=%s,
                        failed_table=%s, failed_step=%s,
                        error_type=%s, error_message=%s
                    WHERE execution_id=%s;
                    """,
                    (
                        status,
                        rows_read,
                        rows_inserted,
                        rows_skipped,
                        failed_table,
                        failed_step,
                        error_type,
                        error_message,
                        execution_id,
                    ),
                )
            connection.commit()

    def persist_watermark_success(
        self,
        execution_id: UUID,
        tenant_id: int,
        execution_watermark: datetime,
        plans: list[IncrementalTablePlan],
    ) -> None:
        with get_metastore_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    for plan in plans:
                        previous = str(
                            plan.previous_watermark or plan.initial_watermark or ""
                        )
                        current = execution_watermark.isoformat()
                        cursor.execute(
                            """
                            INSERT INTO ingest.watermark_history (
                                tenant_id, mapping_version_id, start_value,
                                end_value, candidate_value, is_committed,
                                committed_at, transition_reason_code
                            ) VALUES (%s,%s,%s,%s,%s,TRUE,CURRENT_TIMESTAMP,'INCREMENTAL_SUCCESS');
                            """,
                            (
                                tenant_id,
                                plan.mapping_version_id,
                                previous or None,
                                current,
                                current,
                            ),
                        )
                        cursor.execute(
                            """
                            INSERT INTO ingest.watermark_state (
                                mapping_version_id, tenant_id, current_value,
                                previous_value, candidate_value,
                                watermark_value_type_code, state_updated_at
                            ) VALUES (%s,%s,%s,%s,%s,'TIMESTAMP',CURRENT_TIMESTAMP)
                            ON CONFLICT (mapping_version_id) DO UPDATE SET
                                previous_value=EXCLUDED.previous_value,
                                current_value=EXCLUDED.current_value,
                                candidate_value=NULL,
                                watermark_value_type_code='TIMESTAMP',
                                state_updated_at=CURRENT_TIMESTAMP;
                            """,
                            (
                                plan.mapping_version_id,
                                tenant_id,
                                current,
                                previous or None,
                                current,
                            ),
                        )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def finalize_success(
        self,
        execution_id: UUID,
        tenant_id: int,
        execution_watermark: datetime,
        table_results: list[tuple[IncrementalTablePlan, int, int, int]],
    ) -> None:
        """Advance every table checkpoint and mark the run successful atomically."""
        rows_read = sum(result[1] for result in table_results)
        rows_inserted = sum(result[2] for result in table_results)
        rows_skipped = sum(result[3] for result in table_results)
        with get_metastore_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    for plan, source_count, inserted_count, schema_changes in table_results:
                        previous = str(
                            plan.previous_watermark or plan.initial_watermark or ""
                        )
                        current = execution_watermark.isoformat()
                        cursor.execute(
                            """
                            INSERT INTO ingest.watermark_history (
                                tenant_id, mapping_version_id, start_value,
                                end_value, candidate_value, is_committed,
                                committed_at, transition_reason_code
                            ) VALUES (%s,%s,%s,%s,%s,TRUE,CURRENT_TIMESTAMP,'INCREMENTAL_SUCCESS');
                            """,
                            (
                                tenant_id,
                                plan.mapping_version_id,
                                previous or None,
                                current,
                                current,
                            ),
                        )
                        cursor.execute(
                            """
                            INSERT INTO ingest.watermark_state (
                                mapping_version_id, tenant_id, current_value,
                                previous_value, candidate_value,
                                watermark_value_type_code, state_updated_at
                            ) VALUES (%s,%s,%s,%s,%s,'TIMESTAMP',CURRENT_TIMESTAMP)
                            ON CONFLICT (mapping_version_id) DO UPDATE SET
                                previous_value=EXCLUDED.previous_value,
                                current_value=EXCLUDED.current_value,
                                candidate_value=NULL,
                                watermark_value_type_code='TIMESTAMP',
                                state_updated_at=CURRENT_TIMESTAMP;
                            """,
                            (
                                plan.mapping_version_id,
                                tenant_id,
                                current,
                                previous or None,
                                current,
                            ),
                        )
                        cursor.execute(
                            """
                            UPDATE ingest.incremental_execution_table
                            SET source_count=%s, inserted_count=%s,
                                duplicate_count=%s, schema_change_count=%s,
                                status_code='SUCCESS', ended_at=CURRENT_TIMESTAMP
                            WHERE execution_id=%s AND mapping_version_id=%s;
                            """,
                            (
                                source_count,
                                inserted_count,
                                max(source_count - inserted_count, 0),
                                schema_changes,
                                execution_id,
                                plan.mapping_version_id,
                            ),
                        )
                    cursor.execute(
                        """
                        UPDATE ingest.incremental_execution
                        SET status_code='SUCCESS', ended_at=CURRENT_TIMESTAMP,
                            rows_read=%s, rows_inserted=%s, rows_skipped=%s
                        WHERE execution_id=%s;
                        """,
                        (rows_read, rows_inserted, rows_skipped, execution_id),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def finalize_failure(
        self,
        execution_id: UUID,
        rows_read: int,
        rows_inserted: int,
        rows_skipped: int,
        failed_table: str | None,
        failed_step: str,
        error: Exception,
    ) -> None:
        with get_metastore_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE ingest.incremental_execution_table
                    SET status_code='FAILED', ended_at=CURRENT_TIMESTAMP,
                        error_message=%s
                    WHERE execution_id=%s AND status_code='RUNNING';
                    """,
                    (str(error)[:4000], execution_id),
                )
                cursor.execute(
                    """
                    UPDATE ingest.incremental_execution
                    SET status_code='FAILED', ended_at=CURRENT_TIMESTAMP,
                        rows_read=%s, rows_inserted=%s, rows_skipped=%s,
                        failed_table=%s, failed_step=%s, error_type=%s,
                        error_message=%s
                    WHERE execution_id=%s;
                    """,
                    (
                        rows_read,
                        rows_inserted,
                        rows_skipped,
                        failed_table,
                        failed_step,
                        type(error).__name__,
                        str(error)[:4000],
                        execution_id,
                    ),
                )
            connection.commit()

    def persist_schema_metadata(
        self,
        tenant_id: int,
        dataset_id: int,
        binding_id: int,
        columns: list[ColumnMetadata],
        watermark_column: str,
    ) -> int:
        signature = "\n".join(
            f"{column.ordinal}|{column.name}|{column.data_type}|"
            f"{column.nullable}|{column.default_expression}|{column.is_primary_key}"
            for column in columns
        )
        import hashlib

        schema_hash = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        with get_metastore_connection() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT schema_version_id, version_no
                        FROM catalog.dataset_schema_version
                        WHERE dataset_id=%s AND tenant_id=%s
                          AND is_current=TRUE
                        FOR UPDATE;
                        """,
                        (dataset_id, tenant_id),
                    )
                    current = cursor.fetchone()
                    if current:
                        cursor.execute(
                            "SELECT schema_hash FROM catalog.dataset_schema_version WHERE schema_version_id=%s",
                            (current[0],),
                        )
                        if cursor.fetchone()[0] == schema_hash:
                            schema_version_id = int(current[0])
                        else:
                            cursor.execute(
                                "UPDATE catalog.dataset_schema_version SET is_current=FALSE WHERE schema_version_id=%s",
                                (current[0],),
                            )
                            cursor.execute(
                                """
                                INSERT INTO catalog.dataset_schema_version (
                                    tenant_id,dataset_id,source_binding_id,
                                    version_no,schema_hash,source_code,
                                    change_type_code,is_current
                                ) VALUES (%s,%s,%s,%s,%s,'INCREMENTAL_RUNTIME','ALTER',TRUE)
                                RETURNING schema_version_id;
                                """,
                                (
                                    tenant_id,
                                    dataset_id,
                                    binding_id,
                                    int(current[1]) + 1,
                                    schema_hash,
                                ),
                            )
                            schema_version_id = int(cursor.fetchone()[0])
                            self._insert_schema_fields(
                                cursor,
                                tenant_id,
                                schema_version_id,
                                columns,
                            )
                    else:
                        cursor.execute(
                            """
                            INSERT INTO catalog.dataset_schema_version (
                                tenant_id,dataset_id,source_binding_id,
                                version_no,schema_hash,source_code,
                                change_type_code,is_current
                            ) VALUES (%s,%s,%s,1,%s,'INCREMENTAL_RUNTIME','CREATE',TRUE)
                            RETURNING schema_version_id;
                            """,
                            (tenant_id, dataset_id, binding_id, schema_hash),
                        )
                        schema_version_id = int(cursor.fetchone()[0])
                        self._insert_schema_fields(
                            cursor,
                            tenant_id,
                            schema_version_id,
                            columns,
                        )
                    for column in columns:
                        cursor.execute(
                            """
                            SELECT field_id
                            FROM catalog.dataset_field
                            WHERE schema_version_id=%s AND field_name=%s;
                            """,
                            (schema_version_id, column.name),
                        )
                        field = cursor.fetchone()
                        if field is not None:
                            cursor.execute(
                                """
                                INSERT INTO ingest.incremental_field_metadata (
                                    field_id,tenant_id,is_primary_key,is_watermark
                                ) VALUES (%s,%s,%s,%s)
                                ON CONFLICT (field_id) DO UPDATE SET
                                    is_primary_key=EXCLUDED.is_primary_key,
                                    is_watermark=EXCLUDED.is_watermark,
                                    discovered_at=CURRENT_TIMESTAMP;
                                """,
                                (
                                    field[0],
                                    tenant_id,
                                    column.is_primary_key,
                                    column.name == watermark_column,
                                ),
                            )
                connection.commit()
                return schema_version_id
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    def _insert_schema_fields(
        cursor: Any,
        tenant_id: int,
        schema_version_id: int,
        columns: list[ColumnMetadata],
    ) -> None:
        for column in columns:
            cursor.execute(
                """
                INSERT INTO catalog.dataset_field (
                    tenant_id,schema_version_id,ordinal_no,field_name,
                    field_name_normalized,source_datatype_text,is_nullable,
                    default_expression,is_identity,is_generated
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,FALSE,FALSE);
                """,
                (
                    tenant_id,
                    schema_version_id,
                    column.ordinal,
                    column.name,
                    column.name.lower(),
                    column.data_type,
                    column.nullable,
                    column.default_expression,
                ),
            )