"""
Customer Source Schema Field Inspection
=========================================

Purpose
-------
Inspect the fields belonging to Customer Source Schema Version 6.

WHY:
----
Mapping Version 2 references:

    source dataset  = 7
    source schema   = 6

We need to identify the actual source fields that belong to
schema version 6.

This inspection is READ-ONLY.
No metadata is modified.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display source schema fields for schema version 6.
    """

    print("=" * 70)
    print("CUSTOMER SOURCE SCHEMA FIELDS")
    print("=" * 70)

    # Use the standard metadata connection manager.
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # First discover which metadata table contains the
            # schema-version field information.
            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name,
                    column_name
                FROM information_schema.columns
                WHERE column_name IN (
                    'schema_version_id',
                    'field_id'
                )
                AND table_schema IN (
                    'catalog',
                    'map',
                    'ingest'
                )
                ORDER BY
                    table_schema,
                    table_name,
                    column_name;
                """
            )

            rows = cursor.fetchall()

    # Display candidate tables/columns.
    for row in rows:
        print(row)

    print()
    print(
        "The output identifies the metadata tables that can "
        "resolve source schema fields."
    )

    print("=" * 70)


if __name__ == "__main__":
    main()