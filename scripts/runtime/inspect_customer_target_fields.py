"""
Customer Target Field Inspection
=================================

Purpose
-------
Find the actual target field metadata referenced by:

    map.mapping_field.target_field_id

WHY:
----
mapping_field contains target_field_id rather than the physical
target column name.

The runtime execution engine therefore needs to resolve:

    target_field_id
          |
          v
    target column name

We inspect the metadata relationship before writing runtime code.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect target fields referenced by Mapping Version 2.
    """

    print("=" * 70)
    print("CUSTOMER TARGET FIELD INSPECTION")
    print("=" * 70)

    # Open the metadata database using the existing connection manager.
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # First find which metadata table contains the target
            # field IDs 42, 43, 44 and 45.
            #
            # We search PostgreSQL's catalog rather than guessing the
            # table name.
            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name,
                    column_name
                FROM information_schema.columns
                WHERE column_name = 'target_field_id'
                   OR column_name = 'field_id'
                ORDER BY
                    table_schema,
                    table_name,
                    column_name;
                """
            )

            rows = cursor.fetchall()

    # Display candidate metadata relationships.
    for row in rows:
        print(row)

    print()
    print(
        "The output above shows the metadata tables that may contain "
        "field identifiers."
    )

    print("=" * 70)


if __name__ == "__main__":
    main()