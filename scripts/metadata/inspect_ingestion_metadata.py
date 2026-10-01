"""
Inspect Ingestion Metadata
==========================

Purpose
-------
Inspect the actual metadata tables available in the
Futran metastore for:

    - dtype
    - map
    - ingest

This is a read-only inspection script.

IMPORTANT:
-----------
Do not modify metadata from this script.
We are first understanding the existing metastore
design before implementing the full-load runtime.
"""

from app.db.metastore import get_metastore_connection


SCHEMAS = [
    "dtype",
    "map",
    "ingest",
]


def get_tables(connection, schema_name: str) -> list[str]:
    """
    Return all base tables for a schema.
    """

    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema_name,))
        rows = cursor.fetchall()

    return [row[0] for row in rows]


def get_columns(
    connection,
    schema_name: str,
    table_name: str,
) -> list[tuple]:
    """
    Return column metadata for a table.
    """

    query = """
        SELECT
            ordinal_position,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                schema_name,
                table_name,
            ),
        )

        return cursor.fetchall()


def main() -> None:

    print("=" * 80)
    print("INGESTION METADATA INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:

        for schema_name in SCHEMAS:

            print("\n")
            print("-" * 80)
            print(f"SCHEMA: {schema_name}")
            print("-" * 80)

            tables = get_tables(
                connection,
                schema_name,
            )

            if not tables:
                print("No tables found.")
                continue

            for table_name in tables:

                print(f"\nTABLE: {schema_name}.{table_name}")

                columns = get_columns(
                    connection,
                    schema_name,
                    table_name,
                )

                if not columns:
                    print("  No columns found.")
                    continue

                for (
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                ) in columns:

                    print(
                        f"  {ordinal_position}. "
                        f"{column_name} | "
                        f"{data_type} | "
                        f"Nullable: {is_nullable}"
                    )

    print("\n")
    print("=" * 80)
    print("METADATA INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()