"""
Customer Mapping Field Input Inspection
========================================

Purpose
-------
Inspect the source-field inputs associated with Mapping Version 2.

WHY:
----
The metadata model uses:

    map.mapping_field
            |
            | mapping_field_id
            v
    map.mapping_field_input
            |
            | source_field_id
            v
    catalog.dataset_field

This allows the ingestion engine to resolve source columns
dynamically without hardcoding column names.

This script is READ-ONLY.
No metadata is modified.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display mapping-field inputs and their resolved source fields.
    """

    print("=" * 80)
    print("CUSTOMER MAPPING FIELD INPUTS")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # -----------------------------------------------------
            # Resolve the mapping fields and their source inputs.
            #
            # The JOIN to catalog.dataset_field gives us the
            # actual physical source column name.
            #
            # The JOIN to map.mapping_field gives us the target
            # field associated with the mapping.
            # -----------------------------------------------------
            cursor.execute(
                """
                SELECT
                    mfi.mapping_field_input_id,
                    mfi.mapping_field_id,
                    mfi.source_alias,
                    mfi.source_field_id,
                    mfi.input_role_code,

                    mf.target_field_id,
                    mf.mapping_type_code,
                    mf.ordinal_no,

                    df.field_id,
                    df.field_name,
                    df.field_name_normalized,
                    df.source_datatype_text

                FROM map.mapping_field_input AS mfi

                INNER JOIN map.mapping_field AS mf
                    ON mf.mapping_field_id = mfi.mapping_field_id

                INNER JOIN catalog.dataset_field AS df
                    ON df.field_id = mfi.source_field_id

                WHERE mf.mapping_version_id = %s

                ORDER BY
                    mf.ordinal_no,
                    mfi.mapping_field_input_id;
                """,
                (2,),
            )

            rows = cursor.fetchall()

    # -------------------------------------------------------------
    # Display the resolved source-to-target mapping.
    # -------------------------------------------------------------
    print()

    for row in rows:
        print(row)

    print()
    print(f"Rows found: {len(rows)}")

    # -------------------------------------------------------------
    # Display the expected metadata flow.
    # -------------------------------------------------------------
    print()
    print("-" * 80)
    print("SOURCE FIELD RESOLUTION")
    print("-" * 80)

    for row in rows:
        (
            mapping_field_input_id,
            mapping_field_id,
            source_alias,
            source_field_id,
            input_role_code,
            target_field_id,
            mapping_type_code,
            ordinal_no,
            field_id,
            field_name,
            field_name_normalized,
            source_datatype_text,
        ) = row

        print(
            f"Ordinal {ordinal_no}: "
            f"Mapping Field {mapping_field_id} -> "
            f"Source Field {source_field_id} "
            f"({field_name}) -> "
            f"Target Field {target_field_id}"
        )

    print()
    print("=" * 80)
    print("CUSTOMER MAPPING FIELD INPUT INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()