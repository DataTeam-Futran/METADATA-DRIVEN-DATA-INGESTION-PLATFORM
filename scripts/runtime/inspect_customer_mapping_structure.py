"""
Customer Mapping Structure Inspection
======================================

Purpose
-------
Inspect the metadata relationships used by Mapping Version 2.

WHY:
----
The Full Load Executor must obtain source and target field names
from metadata.

We do not want to hardcode:

    customer_id
    customer_name
    email
    city

inside the execution engine.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect the mapping-field table definition.
    """

    print("=" * 70)
    print("MAPPING FIELD TABLE STRUCTURE")
    print("=" * 70)

    # Use the metadata connection through the context manager.
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # PostgreSQL catalog query returns the actual columns
            # of map.mapping_field.
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type
                FROM information_schema.columns
                WHERE table_schema = 'map'
                  AND table_name = 'mapping_field'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

    # Display the actual table columns.
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