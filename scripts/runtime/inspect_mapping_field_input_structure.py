"""
Mapping Field Input Structure Inspection
=========================================

Purpose
-------
Inspect the exact structure of map.mapping_field_input.

WHY:
----
We need the authoritative column definitions before creating the
runtime field-mapping model.

This script is READ-ONLY.
It does not modify any metadata.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the column definitions of map.mapping_field_input.
    """

    # -------------------------------------------------------------
    # Open a connection to the metadata store.
    # -------------------------------------------------------------
    with get_metastore_connection() as connection:

        # ---------------------------------------------------------
        # Create a cursor for the metadata query.
        # ---------------------------------------------------------
        with connection.cursor() as cursor:

            # -----------------------------------------------------
            # Query PostgreSQL information_schema for the exact
            # column definitions of the mapping input table.
            #
            # Parameterized values are used here instead of
            # embedding strings directly into SQL.
            # -----------------------------------------------------
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
                """,
                ("map", "mapping_field_input"),
            )

            # Fetch all column definitions.
            rows = cursor.fetchall()

    # -------------------------------------------------------------
    # Display the result in a readable format.
    # -------------------------------------------------------------
    print("=" * 80)
    print("MAP.MAPPING_FIELD_INPUT STRUCTURE")
    print("=" * 80)

    for row in rows:
        print(row)

    print()
    print(f"Columns found: {len(rows)}")
    print("=" * 80)


# -------------------------------------------------------------
# Python module entry point.
# -------------------------------------------------------------
if __name__ == "__main__":
    main()