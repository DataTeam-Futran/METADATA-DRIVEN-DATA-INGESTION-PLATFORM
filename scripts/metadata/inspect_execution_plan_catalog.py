"""
Execution Plan Metadata Catalog Inspection
==========================================

Purpose:
    Inspect the existing metadata-store tables that may participate in
    execution planning and runtime orchestration.

Why this step exists:
    Before implementing an ExecutionPlan model or inserting additional
    metadata, we need to understand what the existing database design
    already provides.

Schemas inspected:
    - ingest
    - orch
    - runtime

This script is READ-ONLY.
It does not insert, update, delete, or modify metadata.
"""

from app.db.metastore import get_metastore_connection


# Schemas most relevant to execution planning and runtime processing.
SCHEMAS_TO_INSPECT = (
    "ingest",
    "orch",
    "runtime",
)


def print_section(title: str) -> None:
    """Print a consistent section heading."""

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def inspect_tables(connection) -> list[tuple[str, str]]:
    """
    Discover all base tables in the execution-related schemas.

    Returns:
        List of:
            (schema_name, table_name)

    We use information_schema instead of hard-coding table names because
    the objective of this script is to discover the actual database model.
    """

    print_section("1. EXECUTION-RELATED TABLES")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_schema = ANY(%s)
              AND table_type = 'BASE TABLE'
            ORDER BY table_schema, table_name;
            """,
            (list(SCHEMAS_TO_INSPECT),),
        )

        rows = cursor.fetchall()

    if not rows:
        print("No execution-related tables found.")
        return []

    for schema_name, table_name in rows:
        print(f"{schema_name}.{table_name}")

    print()
    print(f"Tables discovered: {len(rows)}")

    return rows


def inspect_columns(
    connection,
    tables: list[tuple[str, str]],
) -> None:
    """
    Print column definitions for every discovered table.

    This tells us which tables contain references such as:
        mapping_version_id
        source/target connection IDs
        dataset IDs
        load strategy
        pipeline IDs
        execution status
        batch configuration
        runtime identifiers
    """

    print_section("2. TABLE COLUMN DEFINITIONS")

    with connection.cursor() as cursor:

        for schema_name, table_name in tables:

            print()
            print("-" * 100)
            print(f"TABLE: {schema_name}.{table_name}")
            print("-" * 100)

            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
                """,
                (
                    schema_name,
                    table_name,
                ),
            )

            columns = cursor.fetchall()

            for column in columns:
                (
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                ) = column

                print(
                    f"{ordinal_position:>3} | "
                    f"{column_name:<40} | "
                    f"{data_type:<25} | "
                    f"Nullable={is_nullable:<3} | "
                    f"Default={column_default}"
                )


def inspect_foreign_keys(
    connection,
    tables: list[tuple[str, str]],
) -> None:
    """
    Inspect foreign-key relationships for discovered tables.

    This is especially important for execution planning because it reveals
    how orchestration/runtime records connect to mapping, dataset,
    connection, and other metadata.
    """

    print_section("3. FOREIGN KEY RELATIONSHIPS")

    with connection.cursor() as cursor:

        for schema_name, table_name in tables:

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_schema AS referenced_schema,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column
                FROM information_schema.table_constraints tc

                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.constraint_schema = kcu.constraint_schema

                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                   AND ccu.constraint_schema = tc.constraint_schema

                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = %s
                  AND tc.table_name = %s

                ORDER BY
                    tc.constraint_name,
                    kcu.ordinal_position;
                """,
                (
                    schema_name,
                    table_name,
                ),
            )

            foreign_keys = cursor.fetchall()

            if not foreign_keys:
                continue

            print()
            print(f"{schema_name}.{table_name}")

            for foreign_key in foreign_keys:
                (
                    constraint_name,
                    column_name,
                    referenced_schema,
                    referenced_table,
                    referenced_column,
                ) = foreign_key

                print(
                    f"  {column_name} "
                    f"-> "
                    f"{referenced_schema}.{referenced_table}"
                    f".{referenced_column} "
                    f"[{constraint_name}]"
                )


def inspect_mapping_references(connection) -> None:
    """
    Find columns in the inspected schemas whose names suggest that they
    reference mapping configuration.

    This helps identify the existing table intended to connect a mapping
    version to execution/orchestration metadata.
    """

    print_section("4. MAPPING / EXECUTION REFERENCE CANDIDATES")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                table_schema,
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_schema = ANY(%s)
              AND
              (
                  column_name ILIKE '%%mapping%%'
                  OR column_name ILIKE '%%dataset%%'
                  OR column_name ILIKE '%%connection%%'
                  OR column_name ILIKE '%%pipeline%%'
                  OR column_name ILIKE '%%load%%'
                  OR column_name ILIKE '%%batch%%'
                  OR column_name ILIKE '%%execution%%'
                  OR column_name ILIKE '%%run%%'
              )
            ORDER BY
                table_schema,
                table_name,
                ordinal_position;
            """,
            (list(SCHEMAS_TO_INSPECT),),
        )

        rows = cursor.fetchall()

    if not rows:
        print("No candidate execution reference columns found.")
        return

    for row in rows:
        print(
            f"{row[0]}.{row[1]}.{row[2]} "
            f"({row[3]})"
        )


def inspect_sample_rows(
    connection,
    tables: list[tuple[str, str]],
) -> None:
    """
    Show a very small sample from each table.

    Why:
        Table definitions tell us structure, while existing rows show how
        the platform currently uses that structure.

    Only up to three rows are read from each table.
    """

    print_section("5. SAMPLE METADATA")

    with connection.cursor() as cursor:

        for schema_name, table_name in tables:

            # Table names come from information_schema rather than user input.
            # They are therefore controlled metadata identifiers.
            query = (
                f'SELECT * '
                f'FROM "{schema_name}"."{table_name}" '
                f'LIMIT 3;'
            )

            cursor.execute(query)

            rows = cursor.fetchall()

            if not rows:
                continue

            print()
            print("-" * 100)
            print(f"{schema_name}.{table_name}")
            print("-" * 100)

            # Print database column names before the sample values.
            column_names = [
                description.name
                for description in cursor.description
            ]

            print("Columns:")
            print(" | ".join(column_names))

            print("Rows:")

            for row in rows:
                print(row)


def main() -> None:
    """
    Run the complete read-only execution metadata inspection.
    """

    print_section("EXECUTION PLAN METADATA CATALOG INSPECTION")

    with get_metastore_connection() as connection:

        # Discover actual tables first.
        tables = inspect_tables(connection)

        if not tables:
            print_section("INSPECTION COMPLETED")
            print("No tables were available for further inspection.")
            return

        # Inspect the structure of those tables.
        inspect_columns(
            connection,
            tables,
        )

        # Understand how the tables relate to other metadata entities.
        inspect_foreign_keys(
            connection,
            tables,
        )

        # Search specifically for execution-related metadata references.
        inspect_mapping_references(connection)

        # Inspect a small amount of existing metadata to understand how
        # these tables are currently intended to be populated.
        inspect_sample_rows(
            connection,
            tables,
        )

    print_section("EXECUTION PLAN METADATA CATALOG INSPECTION COMPLETED")

    print("Schemas inspected : ingest, orch, runtime")
    print("Operation type    : READ ONLY")
    print("Metadata modified : NO")


if __name__ == "__main__":
    main()