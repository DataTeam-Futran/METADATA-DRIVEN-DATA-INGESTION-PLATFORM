"""
Customer Mapping Source Structure Inspection
==============================================

Purpose
-------
Inspect the actual columns of map.mapping_source.

WHY:
----
We previously assumed that mapping_source had an ordinal_no
column. PostgreSQL confirmed that it does not.

Instead of guessing metadata column names, this script reads
the actual table definition from information_schema.

This is READ-ONLY.
No metadata is inserted, updated, or deleted.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the actual structure of map.mapping_source.
    """

    print("=" * 70)
    print("MAP.MAPPING_SOURCE TABLE STRUCTURE")
    print("=" * 70)

    # Use the existing metadata connection manager.
    #
    # WHY:
    # ----
    # The context manager automatically closes the connection
    # after the inspection is complete.
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # Read the actual PostgreSQL table definition.
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'map'
                  AND table_name = 'mapping_source'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

    # Display the actual columns.
    for ordinal, column_name, data_type in columns:
        print(
            f"{ordinal:>3} | "
            f"{column_name:<40} | "
            f"{data_type}"
        )

    print()
    print(f"Column Count : {len(columns)}")
    print("=" * 70)


if __name__ == "__main__":
    main()