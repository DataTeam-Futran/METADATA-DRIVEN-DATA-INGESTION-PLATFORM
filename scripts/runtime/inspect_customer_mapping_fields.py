"""
Inspect Customer Mapping Fields
================================

Purpose
-------
Read the mapping-field metadata for Mapping Version ID 2.

WHY:
----
The Full Load Executor must not hardcode:

    customer_id
    customer_name
    email
    city

Instead, it must obtain the source-to-target column mapping
from the metadata database.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Read and display mapping fields for Mapping Version 2.
    """

    print("=" * 70)
    print("MAPPING FIELDS FOR VERSION 2")
    print("=" * 70)

    # Use the metadata connection through its context manager.
    #
    # WHY:
    # ----
    # get_metastore_connection() automatically closes the
    # database connection after this block finishes.
    with get_metastore_connection() as connection:

        # Create a cursor for the read-only metadata query.
        with connection.cursor() as cursor:

            # Retrieve all mapping fields belonging to
            # Customer Mapping Version 2.
            cursor.execute(
                """
                SELECT *
                FROM map.mapping_field
                WHERE mapping_version_id = %s
                ORDER BY ordinal_no;
                """,
                (2,),
            )

            # Fetch all mapping-field rows.
            rows = cursor.fetchall()

    # Display the metadata rows after the connection has
    # been safely closed.
    for row in rows:
        print(row)

    print()
    print(f"Mapping Field Count : {len(rows)}")
    print("=" * 70)


if __name__ == "__main__":
    main()