"""Run incremental append loads for Customer and Department."""

from app.db.metastore import get_metastore_connection
from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.incremental_append_executor import IncrementalAppendExecutor
from app.runtime.object_resolver import RuntimeObjectResolver
from scripts.incremental_load.prepare_customer_department_append import (
    SOURCE_CONNECTION_ID,
    TABLES,
    TARGET_CONNECTION_ID,
    WATERMARK_COLUMN,
)


BATCH_SIZE = 1000


def get_execution_scope() -> tuple[int, int]:
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tenant_id, environment_id
                FROM conn.connection_profile
                WHERE connection_id = %s
                  AND status_code = 'ACTIVE';
                """,
                (SOURCE_CONNECTION_ID,),
            )
            source_scope = cursor.fetchone()
            cursor.execute(
                """
                SELECT tenant_id, environment_id
                FROM conn.connection_profile
                WHERE connection_id = %s
                  AND status_code = 'ACTIVE';
                """,
                (TARGET_CONNECTION_ID,),
            )
            target_scope = cursor.fetchone()

    if source_scope is None or target_scope is None:
        raise LookupError("Source or target connection profile is not active.")
    if source_scope != target_scope:
        raise ValueError("Source and target tenant/environment do not match.")
    return int(source_scope[0]), int(source_scope[1])


def get_dataset_id(dataset_code: str, tenant_id: int) -> int:
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT dataset_id
                FROM catalog.dataset
                WHERE tenant_id = %s
                  AND dataset_code = %s
                  AND status_code = 'ACTIVE';
                """,
                (tenant_id, dataset_code),
            )
            row = cursor.fetchone()
    if row is None:
        raise LookupError(
            f"Active dataset {dataset_code!r} is not registered. "
            "Run prepare_customer_department_append first."
        )
    return int(row[0])


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def print_target_preview(table: dict, target_object, tenant_id: int, environment_id: int) -> None:
    target_connector = RuntimeConnectionResolver().resolve(
        target_object.connection_id
    )
    target_connector.connect()
    try:
        columns = [column for column, _ in table["columns"]]
        query = (
            f"SELECT {', '.join(quote_identifier(column) for column in columns)} "
            f"FROM {quote_identifier(target_object.schema_name or '')}."
            f"{quote_identifier(target_object.object_name)} "
            f"ORDER BY {quote_identifier(WATERMARK_COLUMN)} DESC"
        )
        batches = target_connector.read_batches(query, batch_size=BATCH_SIZE)
        try:
            rows = [row for batch in batches for row in batch]
        finally:
            batches.close()

        rendered_rows = [
            [
                "NULL" if value is None else str(value).replace("\r", "\\r").replace("\n", "\\n")
                for value in row
            ]
            for row in rows
        ]
        widths = [
            max([len(column), *(len(row[index]) for row in rendered_rows)])
            for index, column in enumerate(columns)
        ]
        border = "+-" + "-+-".join("-" * width for width in widths) + "-+"

        print(f"  Target table: {target_object.schema_name}.{target_object.object_name}")
        print(border)
        print("| " + " | ".join(column.ljust(width) for column, width in zip(columns, widths)) + " |")
        print(border)
        for row in rendered_rows:
            print("| " + " | ".join(value.ljust(width) for value, width in zip(row, widths)) + " |")
        print(border)
        if not rendered_rows:
            print("  (no rows)")
    finally:
        target_connector.close()


def main() -> None:
    tenant_id, environment_id = get_execution_scope()
    object_resolver = RuntimeObjectResolver()
    connection_resolver = RuntimeConnectionResolver()
    executor = IncrementalAppendExecutor()

    print("INCREMENTAL APPEND LOAD")
    print(f"Tenant: {tenant_id} | Environment: {environment_id}")
    print(f"Source connection: {SOURCE_CONNECTION_ID} | Target connection: {TARGET_CONNECTION_ID}")

    for table in TABLES:
        source_object = object_resolver.resolve(
            dataset_id=get_dataset_id(table["source_code"], tenant_id),
            tenant_id=tenant_id,
            environment_id=environment_id,
        )
        target_object = object_resolver.resolve(
            dataset_id=get_dataset_id(table["target_code"], tenant_id),
            tenant_id=tenant_id,
            environment_id=environment_id,
        )
        if source_object.connection_id != SOURCE_CONNECTION_ID:
            raise ValueError("Source dataset binding does not point to connection 18.")
        if target_object.connection_id != TARGET_CONNECTION_ID:
            raise ValueError("Target dataset binding does not point to connection 11.")

        columns = [column for column, _ in table["columns"]]
        print(f"\n{table['source_table']} -> {target_object.schema_name}.{target_object.object_name}")
        rows_appended = executor.execute(
            source_connector=connection_resolver.resolve(
                source_object.connection_id
            ),
            target_connector=connection_resolver.resolve(
                target_object.connection_id
            ),
            source_schema=source_object.schema_name or "",
            source_table=source_object.object_name,
            target_schema=target_object.schema_name or "",
            target_table=target_object.object_name,
            source_columns=columns,
            target_columns=columns,
            watermark_column=WATERMARK_COLUMN,
            batch_size=BATCH_SIZE,
        )
        if executor.source_rows_read or rows_appended:
            print(f"  Source rows read: {executor.source_rows_read}")
            print(f"  Target rows written: {rows_appended}")
        print_target_preview(table, target_object, tenant_id, environment_id)


if __name__ == "__main__":
    main()