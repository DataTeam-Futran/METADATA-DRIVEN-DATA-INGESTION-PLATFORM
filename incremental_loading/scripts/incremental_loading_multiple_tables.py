"""Discover source tables and append their new rows to matching target tables."""

from typing import Any

from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.incremental_append_executor import IncrementalAppendExecutor


# ---------------------------------------------------------------------------
# Connection and load configuration
# ---------------------------------------------------------------------------

SOURCE_CONNECTION_ID = 18
SOURCE_SCHEMA = "public"
TARGET_CONNECTION_ID = 11
TARGET_DATABASE = "demo_target_db"
TARGET_SCHEMA = "public"
WATERMARK_COLUMN = "last_modified_at"
VERSION_KEY_COLUMN = "_mdip_append_version_id"
BATCH_SIZE = 1000
POSTGRES_TYPE_MAP = {
    "smallint": "SMALLINT",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "numeric": "NUMERIC",
    "decimal": "NUMERIC",
    "real": "REAL",
    "double precision": "DOUBLE PRECISION",
    "boolean": "BOOLEAN",
    "text": "TEXT",
    "character": "TEXT",
    "character varying": "TEXT",
    "date": "DATE",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMPTZ",
    "time without time zone": "TIME",
    "time with time zone": "TIMETZ",
    "uuid": "UUID",
    "json": "JSON",
    "jsonb": "JSONB",
    "bytea": "BYTEA",
}


# ---------------------------------------------------------------------------
# Execution report formatting
# ---------------------------------------------------------------------------

def display_value(value: object) -> str:
    """Return a printable value for report tables."""
    return "Not configured" if value is None or value == "" else str(value)


def print_details_section(title: str, details: list[tuple[str, object]]) -> None:
    """Print aligned property/value rows under a titled report section."""
    label_width = max(len("Property"), *(len(label) for label, _ in details))
    value_width = max(
        len("Details"),
        *(len(display_value(value)) for _, value in details),
    )
    border = "+-" + "-" * label_width + "-+-" + "-" * value_width + "-+"

    print(f"\n{title}")
    print(border)
    print(f"| {'Property':<{label_width}} | {'Details':<{value_width}} |")
    print(border)
    for label, value in details:
        print(f"| {label:<{label_width}} | {display_value(value):<{value_width}} |")
    print(border)


def print_mapping_section(mapping: list[tuple[str, str]]) -> None:
    """Print the source-to-target column mapping as an aligned table."""
    source_width = max(
        len("Source column"),
        *(len(source) for source, _ in mapping),
    )
    target_width = max(
        len("Target column"),
        *(len(target) for _, target in mapping),
    )
    border = "+-" + "-" * source_width + "-+-" + "-" * target_width + "-+"

    print("\nCOLUMN MAPPING")
    print(border)
    print(f"| {'Source column':<{source_width}} | {'Target column':<{target_width}} |")
    print(border)
    for source, target in mapping:
        print(f"| {source:<{source_width}} | {target:<{target_width}} |")
    print(border)


# ---------------------------------------------------------------------------
# Watermark and target-table preparation
# ---------------------------------------------------------------------------

def ensure_source_watermark_trigger(
    source_connector: Any,
    table_name: str,
) -> None:
    """Add the watermark column and refresh it on source inserts/updates."""
    connection = source_connector._require_connection()
    quoted_source = (
        f'{IncrementalAppendExecutor._quote_identifier(SOURCE_SCHEMA)}.'
        f'{IncrementalAppendExecutor._quote_identifier(table_name)}'
    )
    trigger_name = IncrementalAppendExecutor._quote_identifier(
        f"mdip_{table_name}_watermark"
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {quoted_source} "
                f"ADD COLUMN IF NOT EXISTS "
                f"{IncrementalAppendExecutor._quote_identifier(WATERMARK_COLUMN)} "
                "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;"
            )
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION public.mdip_set_last_modified_at()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    NEW.last_modified_at = clock_timestamp();
                    RETURN NEW;
                END;
                $$;
                """
            )
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON {quoted_source};"
            )
            cursor.execute(
                f"CREATE TRIGGER {trigger_name} "
                f"BEFORE INSERT OR UPDATE ON {quoted_source} "
                "FOR EACH ROW EXECUTE FUNCTION public.mdip_set_last_modified_at();"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def ensure_target_table(
    target_connector: Any,
    table_name: str,
    source_columns: list[dict[str, Any]],
) -> None:
    """Create a target table or add missing source columns and version key."""
    connection = target_connector._require_connection()
    quoted_table = (
        f'{IncrementalAppendExecutor._quote_identifier(TARGET_SCHEMA)}.'
        f'{IncrementalAppendExecutor._quote_identifier(table_name)}'
    )
    try:
        with connection.cursor() as cursor:
            definitions = []
            for column in source_columns:
                source_type = str(column["data_type"]).lower()
                target_type = POSTGRES_TYPE_MAP.get(source_type)
                if target_type is None:
                    raise ValueError(
                        f"Unsupported source data type {source_type!r} "
                        f"for {table_name}.{column['column_name']}."
                    )
                column_name = str(column["column_name"])
                nullability = " NOT NULL" if column_name == WATERMARK_COLUMN else ""
                definitions.append(
                    f"{IncrementalAppendExecutor._quote_identifier(column_name)} "
                    f"{target_type}{nullability}"
                )
            definitions.append(
                f"{IncrementalAppendExecutor._quote_identifier(VERSION_KEY_COLUMN)} "
                "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS {quoted_table} "
                f"({', '.join(definitions)});"
            )
            for column in source_columns:
                source_type = str(column["data_type"]).lower()
                target_type = POSTGRES_TYPE_MAP[source_type]
                column_name = str(column["column_name"])
                cursor.execute(
                    f"ALTER TABLE {quoted_table} ADD COLUMN IF NOT EXISTS "
                    f"{IncrementalAppendExecutor._quote_identifier(column_name)} "
                    f"{target_type};"
                )
            cursor.execute(
                f"ALTER TABLE {quoted_table} "
                f"ADD COLUMN IF NOT EXISTS "
                f"{IncrementalAppendExecutor._quote_identifier(VERSION_KEY_COLUMN)} "
                "BIGINT GENERATED ALWAYS AS IDENTITY;"
            )
            cursor.execute(
                """
                SELECT constraint_row.conname,
                       array_agg(attribute_row.attname ORDER BY key_column.ordinality)
                FROM pg_constraint AS constraint_row
                JOIN pg_class AS table_row
                  ON table_row.oid = constraint_row.conrelid
                JOIN pg_namespace AS schema_row
                  ON schema_row.oid = table_row.relnamespace
                CROSS JOIN LATERAL unnest(constraint_row.conkey)
                  WITH ORDINALITY AS key_column(attnum, ordinality)
                JOIN pg_attribute AS attribute_row
                  ON attribute_row.attrelid = table_row.oid
                 AND attribute_row.attnum = key_column.attnum
                WHERE constraint_row.contype = 'p'
                  AND schema_row.nspname = %s
                  AND table_row.relname = %s
                GROUP BY constraint_row.conname;
                """,
                (TARGET_SCHEMA, table_name),
            )
            primary_key = cursor.fetchone()
            if primary_key and primary_key[1] != [VERSION_KEY_COLUMN]:
                constraint_name = IncrementalAppendExecutor._quote_identifier(
                    primary_key[0]
                )
                cursor.execute(
                    f"ALTER TABLE {quoted_table} "
                    f"DROP CONSTRAINT {constraint_name};"
                )
                cursor.execute(
                    f"ALTER TABLE {quoted_table} "
                    f"ADD PRIMARY KEY "
                    f"({IncrementalAppendExecutor._quote_identifier(VERSION_KEY_COLUMN)});"
                )
                print(
                    f"{TARGET_SCHEMA}.{table_name} primary key changed to "
                    f"{VERSION_KEY_COLUMN}; existing rows were preserved."
                )
            elif primary_key is None:
                cursor.execute(
                    f"ALTER TABLE {quoted_table} ADD PRIMARY KEY "
                    f"({IncrementalAppendExecutor._quote_identifier(VERSION_KEY_COLUMN)});"
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def get_shared_column_mapping(
    source_connector: Any,
    target_connector: Any,
    table_name: str,
) -> list[tuple[str, str]]:
    """Map source fields to same-named target fields and require a watermark."""
    source_columns = source_connector.list_columns(SOURCE_SCHEMA, table_name)
    target_columns = target_connector.list_columns(TARGET_SCHEMA, table_name)
    target_names = {column["column_name"] for column in target_columns}
    mapping = [
        (column["column_name"], column["column_name"])
        for column in source_columns
        if column["column_name"] in target_names
        and column["column_name"] != VERSION_KEY_COLUMN
    ]

    if not mapping:
        raise ValueError(
            f"Source and target tables have no matching columns: {table_name}."
        )
    if not any(source == WATERMARK_COLUMN for source, _ in mapping):
        raise ValueError(
            f"Both tables must contain the watermark column {WATERMARK_COLUMN!r}."
        )
    return mapping


# ---------------------------------------------------------------------------
# Target data output
# ---------------------------------------------------------------------------

def print_target_table(
    target_connector: Any,
    table_name: str,
    columns: list[str],
) -> int:
    """Print every target row in an aligned table and return the row count."""
    quoted_columns = ", ".join(
        IncrementalAppendExecutor._quote_identifier(column)
        for column in columns
    )
    query = (
        f"SELECT {quoted_columns} FROM "
        f'{IncrementalAppendExecutor._quote_identifier(TARGET_SCHEMA)}.'
        f'{IncrementalAppendExecutor._quote_identifier(table_name)} '
        f"ORDER BY "
        f"{IncrementalAppendExecutor._quote_identifier(WATERMARK_COLUMN)} DESC"
    )
    batches = target_connector.read_batches(query, batch_size=BATCH_SIZE)
    try:
        rows = [row for batch in batches for row in batch]
    finally:
        batches.close()

    rendered_rows = [
        [
            "NULL"
            if value is None
            else str(value).replace("\r", "\\r").replace("\n", "\\n")
            for value in row
        ]
        for row in rows
    ]
    widths = [
        max([len(column), *(len(row[index]) for row in rendered_rows)])
        for index, column in enumerate(columns)
    ]
    border = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    print(f"\nTARGET TABLE OUTPUT: {TARGET_DATABASE}.{TARGET_SCHEMA}.{table_name}")
    print(f"Rows displayed: {len(rows)}")
    print(border)
    print(
        "| "
        + " | ".join(
            column.ljust(width)
            for column, width in zip(columns, widths)
        )
        + " |"
    )
    print(border)
    for row in rendered_rows:
        print(
            "| "
            + " | ".join(
                value.ljust(width)
                for value, width in zip(row, widths)
            )
            + " |"
        )
    print(border)
    if not rendered_rows:
        print("(no rows)")
    return len(rows)


# ---------------------------------------------------------------------------
# Per-table incremental execution
# ---------------------------------------------------------------------------

def run_table(
    source_connector: Any,
    target_connector: Any,
    table_name: str,
) -> tuple[int, int, int]:
    """Run one table's setup, incremental append, and target report."""
    source_connector.connect()
    target_connector.connect()
    try:
        ensure_source_watermark_trigger(source_connector, table_name)
        source_metadata = source_connector.list_columns(SOURCE_SCHEMA, table_name)
        ensure_target_table(target_connector, table_name, source_metadata)
        mapping = get_shared_column_mapping(
            source_connector,
            target_connector,
            table_name,
        )
        source_columns = [source for source, _ in mapping]
        target_columns = [target for _, target in mapping]
        print(f"\n{'=' * 72}")
        print(f"INCREMENTAL APPEND: {table_name}")
        print("=" * 72)
        print_details_section(
            "EXECUTION SPECIFICATIONS",
            [
                ("Load mode", "Incremental append; preserve prior target rows"),
                ("Watermark column", WATERMARK_COLUMN),
                (
                    "Source update tracking",
                    "Trigger refreshes watermark on insert/update",
                ),
                ("Batch size", BATCH_SIZE),
                ("Target version key", VERSION_KEY_COLUMN),
            ],
        )
        print_details_section(
            "SOURCE CONNECTION DETAILS",
            [
                ("Connection ID", source_connector.metadata.connection_id),
                ("Connection name", source_connector.metadata.connection_name),
                ("Host", source_connector.metadata.host_name),
                ("Port", source_connector.metadata.port_no),
                ("Database", source_connector.metadata.database_name),
                ("Schema", SOURCE_SCHEMA),
                ("Table", table_name),
            ],
        )
        print_details_section(
            "TARGET CONNECTION DETAILS",
            [
                ("Connection ID", target_connector.metadata.connection_id),
                ("Connection name", target_connector.metadata.connection_name),
                ("Host", target_connector.metadata.host_name),
                ("Port", target_connector.metadata.port_no),
                ("Database", target_connector.metadata.database_name),
                ("Schema", TARGET_SCHEMA),
                ("Table", table_name),
            ],
        )
        print_mapping_section(mapping)
    finally:
        source_connector.close()
        target_connector.close()

    executor = IncrementalAppendExecutor()
    rows_appended = executor.execute(
        source_connector=source_connector,
        target_connector=target_connector,
        source_schema=SOURCE_SCHEMA,
        source_table=table_name,
        target_schema=TARGET_SCHEMA,
        target_table=table_name,
        source_columns=source_columns,
        target_columns=target_columns,
        watermark_column=WATERMARK_COLUMN,
        batch_size=BATCH_SIZE,
    )
    print_details_section(
        "LOAD ROW COUNTS",
        [
            ("Source rows returned after watermark filter", executor.source_rows_read),
            ("Target rows written", rows_appended),
        ],
    )

    target_connector.connect()
    try:
        target_rows = print_target_table(target_connector, table_name, target_columns)
    finally:
        target_connector.close()
    return executor.source_rows_read, rows_appended, target_rows


# ---------------------------------------------------------------------------
# Multi-table entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Discover source tables and append each to the target database."""
    resolver = RuntimeConnectionResolver()
    source_connector = resolver.resolve(SOURCE_CONNECTION_ID)
    target_connector = resolver.resolve(
        TARGET_CONNECTION_ID,
        database_name_override=TARGET_DATABASE,
    )
    source_connector.connect()
    try:
        source_tables = source_connector.list_tables(SOURCE_SCHEMA)
    finally:
        source_connector.close()

    if not source_tables:
        raise LookupError(f"No source tables found in {SOURCE_SCHEMA!r}.")

    print("=" * 72)
    print("MULTI-TABLE INCREMENTAL APPEND")
    print(f"Source: {source_connector.metadata.database_name}.{SOURCE_SCHEMA}")
    print(f"Target: {TARGET_DATABASE}.{TARGET_SCHEMA}")
    print(f"Source tables discovered: {len(source_tables)}")
    print("Target tables use the same names as their source tables.")
    print("=" * 72)

    totals = {"source_read": 0, "target_written": 0, "target_total": 0}
    failures: list[tuple[str, str]] = []
    for table_name in source_tables:
        try:
            source_read, target_written, target_total = run_table(
                source_connector,
                target_connector,
                table_name,
            )
            totals["source_read"] += source_read
            totals["target_written"] += target_written
            totals["target_total"] += target_total
        except Exception as error:
            failures.append((table_name, str(error)))
            print(f"\nFAILED TABLE: {table_name}: {error}")

    print_details_section(
        "MULTI-TABLE TOTALS",
        [
            ("Tables discovered", len(source_tables)),
            ("Tables failed", len(failures)),
            ("Source rows returned", totals["source_read"]),
            ("Target rows written", totals["target_written"]),
            ("Target rows across processed tables", totals["target_total"]),
        ],
    )
    if failures:
        raise RuntimeError(
            "One or more source tables failed: "
            + "; ".join(f"{table}: {error}" for table, error in failures)
        )


if __name__ == "__main__":
    main()