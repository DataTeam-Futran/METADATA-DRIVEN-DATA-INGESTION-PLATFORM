"""Metadata-driven incremental append/update CLI for PostgreSQL tables."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root in sys.path is False:
        sys.path.insert(0, project_root)

import psycopg
from psycopg import sql

from app.connectors.factory import ConnectorFactory
from app.connectors.register_connectors import create_connector_registry
from app.db.metastore import get_metastore_connection
from app.runtime.multi_table_full_load_executor import MultiTableFullLoadExecutor
from app.runtime.selective_table_full_load_executor import (
    _format_table,
    parse_table_selection,
    render_discovery_report,
    render_selected_tables,
)
from app.runtime.unified_full_load_cli import (
    _onboard_table,
    _print_connection,
    _print_target_preparation,
    _prompt_for_missing_arguments,
    _prompt_for_missing_scope,
    _resolve_scope_from_bindings,
)
from app.services.connection_service import ConnectionService
from app.services.governance_lifecycle_service import GovernanceLifecycleService

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover tables and apply governed incremental append/update loads."
    )
    parser.add_argument("--source-connection-id", type=int)
    parser.add_argument("--target-connection-id", type=int)
    parser.add_argument("--source-schema")
    parser.add_argument("--target-schema")
    parser.add_argument("--tenant-id", type=int)
    parser.add_argument("--project-id", type=int)
    parser.add_argument("--environment-id", type=int)
    parser.add_argument("--datatype-mapping-set-id", type=int)
    parser.add_argument("--tables", nargs="+", help="ALL or table names/indexes.")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--watermark-column", default="last_modified_date")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--auto-governance", action="store_true")
    return parser


def _select_tables(requested: list[str] | None, discovered: list[str]) -> list[str]:
    if requested is None:
        print("\nTABLE LOAD SCOPE")
        print("  1. ALL discovered tables")
        print("  2. Select specific tables")
        choice = input("Choose 1 or 2: ").strip()
        if choice == "1":
            return list(discovered)
        requested = [item.strip() for item in input("Enter table numbers or names, comma separated: ").split(",")]
    value = ",".join(requested)
    return parse_table_selection(value, discovered)


def _quoted(identifier: str) -> sql.Identifier:
    return sql.Identifier(identifier)


def _primary_keys(connection: Any, schema: str, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT a.attname
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            JOIN pg_index i ON i.indrelid=c.oid
            JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=ANY(i.indkey)
            WHERE n.nspname=%s AND c.relname=%s AND c.relkind IN ('r', 'p') AND i.indisprimary
            ORDER BY array_position(i.indkey, a.attnum)
            """,
            (schema, table),
        )
        return [row[0] for row in cursor.fetchall()]


def _prompt_for_incremental_load_confirmation() -> bool:
    while True:
        try:
            answer = input(
                "\nStart the incremental load now? This uses append/update logic "
                "based on the watermark column [y/N]: "
            ).strip().casefold()
        except (EOFError, OSError):
            return False
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        print("Enter y or n.")


def _column_names(connection: Any, schema: str, table: str) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [row[0] for row in cursor.fetchall()]


def _resolve_connector(connection_id: int):
    metadata = ConnectionService().get_connection_metadata(connection_id)
    return ConnectorFactory(create_connector_registry()).create(metadata)


def _ensure_logical_primary_key(
    connector: Any, schema: str, table: str
) -> None:
    connector.connect()
    connection = connector._connection
    columns = _column_names(connection, schema, table)
    lowered_columns = {name.casefold(): name for name in columns}
    table_base = table.strip('"').casefold()
    preferred_names = [f"{table_base}_id", "id"]
    primary_keys = _primary_keys(connection, schema, table)
    if primary_keys:
        return
    candidate = next((lowered_columns[name] for name in preferred_names if name in lowered_columns), None)
    if candidate is None:
        candidate = next((name for key, name in lowered_columns.items() if key.endswith("_id")), None)
    if candidate is None:
        return
    table_sql = sql.SQL(".").join((_quoted(schema), _quoted(table)))
    column_sql = _quoted(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER TABLE {table} ADD PRIMARY KEY ({column})").format(
                    table=table_sql, column=column_sql
                )
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _ensure_watermark_column(
    connector: Any, schema: str, table: str, watermark_column: str
) -> None:
    connector.connect()
    connection = connector._connection
    table_sql = sql.SQL(".").join((_quoted(schema), _quoted(table)))
    column_sql = _quoted(watermark_column)
    statements = (
        sql.SQL("ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP").format(table=table_sql, column=column_sql),
        sql.SQL("UPDATE {table} SET {column}=CURRENT_TIMESTAMP WHERE {column} IS NULL").format(table=table_sql, column=column_sql),
    )
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _configure_incremental_metadata(
    *, tenant_id: int, mapping_version_id: int, watermark_field_id: int,
    watermark_column: str, batch_size: int,
) -> None:
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE map.mapping_version
                   SET load_type_code='INCREMENTAL',
                       load_strategy_code='APPEND_UPDATE',
                       config_hash=%s,
                       updated_at=now()
                 WHERE mapping_version_id=%s AND tenant_id=%s
                """,
                (f"INCREMENTAL_APPEND_UPDATE:{watermark_column}:{batch_size}", mapping_version_id, tenant_id),
            )
            cursor.execute(
                """
                UPDATE ingest.load_config
                   SET load_type_code='INCREMENTAL',
                       batch_size=%s,
                       truncate_before_load=FALSE,
                       is_active=TRUE
                 WHERE mapping_version_id=%s
                """,
                (batch_size, mapping_version_id),
            )
            cursor.execute(
                """
                UPDATE ingest.target_load_config
                   SET load_method_code='MERGE',
                       commit_size=%s,
                       auto_create_target=FALSE,
                       alter_target_policy_code='UPDATE',
                       transaction_mode_code='AUTO',
                       target_prepare_action_code='NONE'
                 WHERE mapping_version_id=%s
                   AND tenant_id=%s
                """,
                (batch_size, mapping_version_id, tenant_id),
            )
            cursor.execute(
                """
                INSERT INTO ingest.target_load_config (
                    mapping_version_id, tenant_id, load_method_code, commit_size,
                    auto_create_target, alter_target_policy_code,
                    transaction_mode_code, write_timeout_seconds,
                    target_prepare_action_code, target_schema_policy_code,
                    constraint_apply_policy_code, index_apply_policy_code
                )
                SELECT %s, %s, 'MERGE', %s, FALSE, 'UPDATE',
                       'AUTO', 600, 'NONE', 'CREATE_IF_MISSING',
                       'APPLY_AFTER_LOAD', 'APPLY_AFTER_LOAD'
                WHERE NOT EXISTS (
                    SELECT 1 FROM ingest.target_load_config
                    WHERE mapping_version_id=%s AND tenant_id=%s
                )
                """,
                (mapping_version_id, tenant_id, batch_size, mapping_version_id, tenant_id),
            )
            cursor.execute(
                """
                INSERT INTO ingest.incremental_config (
                    mapping_version_id, tenant_id, incremental_mode_code,
                    watermark_field_id, boundary_mode_code, lookback_value,
                    late_arrival_policy_code, delete_detection_code,
                    startup_mode_code, initial_watermark_value,
                    high_watermark_capture_code
                ) VALUES (%s,%s,'CHANGE_TIMESTAMP',%s,'EXCLUSIVE_START','0 seconds',
                          'IGNORE','NONE','FROM_BEGINNING','1970-01-01T00:00:00Z','SNAPSHOT_AT_END')
                ON CONFLICT (mapping_version_id) DO UPDATE SET
                    watermark_field_id=EXCLUDED.watermark_field_id,
                    incremental_mode_code=EXCLUDED.incremental_mode_code,
                    boundary_mode_code=EXCLUDED.boundary_mode_code,
                    updated_at=now()
                """,
                (mapping_version_id, tenant_id, watermark_field_id),
            )
            cursor.execute(
                """
                INSERT INTO ingest.watermark_state (
                    mapping_version_id, tenant_id, current_value,
                    previous_value, candidate_value, watermark_value_type_code,
                    state_updated_at
                ) VALUES (%s,%s,'1970-01-01T00:00:00Z',NULL,NULL,'TIMESTAMP',now())
                ON CONFLICT (mapping_version_id) DO NOTHING
                """,
                (mapping_version_id, tenant_id),
            )
        connection.commit()


def _load_incremental(
    *, source_connector: Any, target_connector: Any,
    source_schema: str, target_schema: str, table_name: str,
    columns: list[str], watermark_column: str, batch_size: int,
    mapping_version_id: int, tenant_id: int,
) -> tuple[int, datetime | None]:
    source = source_connector
    target = target_connector
    source.connect()
    target.connect()
    source_connection = source._connection
    target_connection = target._connection

    with get_metastore_connection() as control:
        with control.cursor() as cursor:
            cursor.execute(
                "SELECT COALESCE(current_value, '1970-01-01T00:00:00Z') FROM ingest.watermark_state WHERE mapping_version_id=%s AND tenant_id=%s",
                (mapping_version_id, tenant_id),
            )
            row = cursor.fetchone()
            watermark = row[0] if row else "1970-01-01T00:00:00Z"

    primary_keys = _primary_keys(source_connection, source_schema, table_name)
    if not primary_keys:
        raise ValueError(f"Incremental load requires a primary key on source table {source_schema}.{table_name}.")
    target_keys = _primary_keys(target_connection, target_schema, table_name)
    if set(primary_keys) != set(target_keys):
        target_columns = _column_names(target_connection, target_schema, table_name)
        missing = [key for key in primary_keys if key not in target_columns]
        if missing:
            raise ValueError(
                f"Source and target primary keys differ for {source_schema}.{table_name}; "
                f"target is missing {missing}."
            )
        with target_connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid=to_regclass(%s) AND contype='p'
                """,
                (f'{target_schema}.{table_name}',),
            )
            for (constraint_name,) in cursor.fetchall():
                cursor.execute(sql.SQL("ALTER TABLE {} DROP CONSTRAINT {}").format(
                    sql.SQL(".").join((_quoted(target_schema), _quoted(table_name))),
                    sql.Identifier(constraint_name),
                ))
            cursor.execute(sql.SQL("ALTER TABLE {} ADD PRIMARY KEY ({})").format(
                sql.SQL(".").join((_quoted(target_schema), _quoted(table_name))),
                sql.SQL(", ").join(_quoted(key) for key in primary_keys),
            ))
        target_connection.commit()

    quoted_source = sql.SQL(".").join((_quoted(source_schema), _quoted(table_name)))
    quoted_watermark = _quoted(watermark_column)
    select_query = sql.SQL("SELECT {columns} FROM {table} WHERE {watermark} > %s ORDER BY {watermark}").format(
        columns=sql.SQL(", ").join(_quoted(column) for column in columns),
        table=quoted_source,
        watermark=quoted_watermark,
    )

    rows: list[tuple[Any, ...]] = []
    inserted_or_updated = 0
    highest = None
    target_connection.rollback()
    try:
        with source_connection.cursor() as source_cursor:
            source_cursor.execute(select_query, (watermark,))
            for row in source_cursor.fetchall():
                rows.append(tuple(row))
                position = columns.index(watermark_column)
                candidate = row[position]
                if candidate is not None and (highest is None or candidate > highest):
                    highest = candidate
                if len(rows) >= batch_size:
                    inserted_or_updated += _merge_rows(target_connection, target_schema, table_name, columns, primary_keys, rows)
                    rows.clear()
        if rows:
            inserted_or_updated += _merge_rows(target_connection, target_schema, table_name, columns, primary_keys, rows)
        target_connection.commit()

        if highest is not None:
            with get_metastore_connection() as control:
                with control.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE ingest.watermark_state
                           SET previous_value=current_value,
                               candidate_value=%s::text,
                               current_value=%s::text,
                               state_updated_at=now(), updated_at=now()
                         WHERE mapping_version_id=%s AND tenant_id=%s
                        """,
                        (str(highest), str(highest), mapping_version_id, tenant_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO ingest.watermark_history (
                            tenant_id, mapping_version_id, task_run_id,
                            start_value, end_value, candidate_value,
                            is_committed, committed_at, transition_reason_code
                        ) VALUES (%s,%s,NULL,%s,%s,%s,TRUE,now(),'INCREMENTAL_LOAD')
                        """,
                        (tenant_id, mapping_version_id, str(watermark), str(highest), str(highest)),
                    )
                control.commit()
        return inserted_or_updated, highest
    except Exception:
        target_connection.rollback()
        raise


def _merge_rows(connection: Any, schema: str, table: str, columns: list[str], keys: list[str], rows: list[tuple[Any, ...]]) -> int:
    table_sql = sql.SQL(".").join((_quoted(schema), _quoted(table)))
    column_sql = sql.SQL(", ").join(_quoted(column) for column in columns)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    insert = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({values})").format(
        table=table_sql, columns=column_sql, values=placeholders
    )
    conflict_columns = sql.SQL(", ").join(_quoted(key) for key in keys)
    non_key_columns = [column for column in columns if column not in keys]
    if non_key_columns:
        assignments = sql.SQL(", ").join(
            sql.SQL("{column}=EXCLUDED.{column}").format(column=_quoted(column))
            for column in non_key_columns
        )
        statement = sql.SQL("{insert} ON CONFLICT ({keys}) DO UPDATE SET {assignments}").format(
            insert=insert, keys=conflict_columns, assignments=assignments
        )
    else:
        statement = sql.SQL("{insert} ON CONFLICT ({keys}) DO NOTHING").format(
            insert=insert, keys=conflict_columns
        )
    with connection.cursor() as cursor:
        cursor.executemany(statement, rows)
    return len(rows)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    _prompt_for_missing_arguments(args)
    _resolve_scope_from_bindings(args)
    _prompt_for_missing_scope(args)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    connection_service = ConnectionService()
    source_metadata = connection_service.get_connection_metadata(args.source_connection_id)
    target_metadata = connection_service.get_connection_metadata(args.target_connection_id)

    executor = MultiTableFullLoadExecutor(
        source_connection_id=args.source_connection_id,
        target_connection_id=args.target_connection_id,
        batch_size=args.batch_size,
    )
    discovered = executor.discover_source_tables(args.source_schema)
    print(render_discovery_report(args.source_schema, discovered))
    if not discovered:
        raise LookupError(f"No source tables found in schema {args.source_schema!r}.")
    selected = _select_tables(args.tables, discovered)
    print(render_selected_tables(selected))

    source_connector = _resolve_connector(args.source_connection_id)
    target_connector = _resolve_connector(args.target_connection_id)
    for table_name in selected:
        _ensure_logical_primary_key(source_connector, args.source_schema, table_name)
        _ensure_watermark_column(
            source_connector, args.source_schema, table_name,
            args.watermark_column,
        )

    preparations = executor.prepare_target_tables(args.source_schema, args.target_schema, selected)
    for table_name in selected:
        _ensure_logical_primary_key(target_connector, args.target_schema, table_name)
        _ensure_watermark_column(
            target_connector, args.target_schema, table_name,
            args.watermark_column,
        )
    _print_target_preparation(preparations, args.target_schema)
    prep_by_table = {item.table_name: item for item in preparations}
    summary: list[list[str]] = []
    success = True
    load_requested = args.execute or _prompt_for_incremental_load_confirmation()

    for table_name in selected:
        try:
            prep = prep_by_table[table_name]
            source_names = [c["column_name"] for c in prep.source_columns]
            if args.watermark_column not in source_names:
                raise ValueError(
                    f"Source table {args.source_schema}.{table_name} must contain mandatory watermark column {args.watermark_column}."
                )
            metadata = _onboard_table(
                source_metadata=source_metadata,
                target_metadata=target_metadata,
                source_columns=prep.source_columns,
                target_columns=prep.target_columns,
                source_schema=args.source_schema,
                target_schema=args.target_schema,
                table_name=table_name,
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                environment_id=args.environment_id,
                batch_size=args.batch_size,
                datatype_mapping_set_id=args.datatype_mapping_set_id,
            )
            governance = GovernanceLifecycleService().activate_and_publish(
                tenant_id=args.tenant_id,
                project_id=args.project_id,
                environment_id=args.environment_id,
                mapping_version_id=int(metadata["mapping_version_id"]),
                pipeline_version_id=int(metadata["pipeline_version_id"]),
                auto_governance=True if args.auto_governance else None,
            )

            source_field_id = next(
                int(item["field_id"])
                for item in metadata["source_fields"]
                if item["field_name"] == args.watermark_column
            )
            _configure_incremental_metadata(
                tenant_id=args.tenant_id,
                mapping_version_id=int(metadata["mapping_version_id"]),
                watermark_field_id=source_field_id,
                watermark_column=args.watermark_column,
                batch_size=args.batch_size,
            )

            if args.execute:
                source_connector = _resolve_connector(args.source_connection_id)
                target_connector = _resolve_connector(args.target_connection_id)
                rows, highest = _load_incremental(
                    source_connector=source_connector,
                    target_connector=target_connector,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                    table_name=table_name,
                    columns=[c["column_name"] for c in sorted(prep.source_columns, key=lambda c: c["ordinal_position"])],
                    watermark_column=args.watermark_column,
                    batch_size=args.batch_size,
                    mapping_version_id=int(metadata["mapping_version_id"]),
                    tenant_id=args.tenant_id,
                )
                status = "SUCCESS"
                error = ""
            elif load_requested:
                source_connector = _resolve_connector(args.source_connection_id)
                target_connector = _resolve_connector(args.target_connection_id)
                rows, highest = _load_incremental(
                    source_connector=source_connector,
                    target_connector=target_connector,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                    table_name=table_name,
                    columns=[c["column_name"] for c in sorted(prep.source_columns, key=lambda c: c["ordinal_position"])],
                    watermark_column=args.watermark_column,
                    batch_size=args.batch_size,
                    mapping_version_id=int(metadata["mapping_version_id"]),
                    tenant_id=args.tenant_id,
                )
                status = "SUCCESS"
                error = ""
            else:
                rows = 0
                status = "NOT EXECUTED"
                error = "User declined incremental load."
            summary.append([f"{args.source_schema}.{table_name}", f"{args.target_schema}.{table_name}", status, str(rows), governance.mapping_status, governance.pipeline_status, error])
        except Exception as exc:
            success = False
            logger.exception("Incremental load failed for %s.", table_name)
            summary.append([f"{args.source_schema}.{table_name}", f"{args.target_schema}.{table_name}", "FAILED", "0", "Unknown", "Unknown", f"{type(exc).__name__}: {exc}"])

    print("\nINCREMENTAL TABLE EXECUTION STATUS")
    for line in _format_table(
        ["Source Table", "Target Table", "Status", "Rows Inserted/Updated", "Mapping", "Pipeline", "Error Details"],
        summary,
    ):
        print(line)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
