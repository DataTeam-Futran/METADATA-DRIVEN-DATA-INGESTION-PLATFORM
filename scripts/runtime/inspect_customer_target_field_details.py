"""
Customer Target Field Details
==============================

Purpose
-------
Resolve the target_field_id values used by Mapping Version 2.

For the Customer mapping, mapping_field contains:

    target_field_id = 42, 43, 44, 45

These IDs should point to catalog.dataset_field.field_id.

WHY:
----
The runtime engine needs the physical target column names
instead of relying on hardcoded column names.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display target field metadata for Mapping Version 2.
    """

    print("=" * 70)
    print("CUSTOMER TARGET FIELD DETAILS")
    print("=" * 70)

    # Open the metadata database using the standard connection manager.
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # Resolve the target field IDs referenced by the mapping.
            cursor.execute(
                """
                SELECT
                    mf.mapping_field_id,
                    mf.ordinal_no,
                    mf.mapping_type_code,
                    mf.target_field_id,
                    df.*
                FROM map.mapping_field AS mf
                INNER JOIN catalog.dataset_field AS df
                    ON df.field_id = mf.target_field_id
                WHERE mf.mapping_version_id = %s
                ORDER BY mf.ordinal_no;
                """,
                (2,),
            )

            rows = cursor.fetchall()

    # Display the complete joined metadata.
    for row in rows:
        print(row)

    print()
    print(f"Resolved Target Field Count : {len(rows)}")
    print("=" * 70)


if __name__ == "__main__":
    main()