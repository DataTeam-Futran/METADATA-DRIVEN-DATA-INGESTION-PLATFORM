"""
Customer Mapping Input Metadata Inspection
===========================================

Purpose
-------
Identify how Mapping Version 2 represents the source-side field
for each mapping field.

WHY:
----
The current map.mapping_field table contains:

    target_field_id

but does not contain:

    source_field_id

Therefore, before implementing the Full Load Executor, we must
identify the metadata structure that connects a mapping field to
its source field or source expression.

IMPORTANT:
----------
This script is READ-ONLY.

No INSERT, UPDATE, DELETE, or other metadata modification is
performed.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect metadata tables that may contain mapping source inputs.
    """

    # -------------------------------------------------------------
    # Display the purpose of this inspection.
    # -------------------------------------------------------------
    print("=" * 80)
    print("CUSTOMER MAPPING INPUT METADATA INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # -----------------------------------------------------
            # Step 1:
            # Find all metadata tables containing mapping_field_id.
            #
            # This helps us identify tables that may extend
            # map.mapping_field with source-side information.
            # -----------------------------------------------------
            print()
            print("-" * 80)
            print("1. TABLES CONTAINING mapping_field_id")
            print("-" * 80)

            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name,
                    column_name
                FROM information_schema.columns
                WHERE column_name = 'mapping_field_id'
                ORDER BY
                    table_schema,
                    table_name;
                """
            )

            mapping_field_reference_rows = cursor.fetchall()

            for row in mapping_field_reference_rows:
                print(row)

            print(
                f"Rows found: {len(mapping_field_reference_rows)}"
            )

            # -----------------------------------------------------
            # Step 2:
            # Find columns that look like source-field references.
            #
            # We are not assuming a table name.
            #
            # The metadata model may use names such as:
            #
            #     source_field_id
            #     input_field_id
            #     field_id
            #     source_expression
            #
            # This query helps us discover the actual model.
            # -----------------------------------------------------
            print()
            print("-" * 80)
            print("2. CANDIDATE SOURCE / INPUT FIELD COLUMNS")
            print("-" * 80)

            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name,
                    column_name
                FROM information_schema.columns
                WHERE
                    column_name ILIKE '%source%'
                    OR column_name ILIKE '%input%'
                    OR column_name ILIKE '%field%'
                AND table_schema NOT IN (
                    'pg_catalog',
                    'information_schema'
                )
                ORDER BY
                    table_schema,
                    table_name,
                    column_name;
                """
            )

            candidate_rows = cursor.fetchall()

            for row in candidate_rows:
                print(row)

            print(
                f"Rows found: {len(candidate_rows)}"
            )

            # -----------------------------------------------------
            # Step 3:
            # Inspect the existing mapping fields.
            #
            # This confirms exactly what Mapping Version 2 stores
            # and gives us the mapping_field_id values that need
            # source-side resolution.
            # -----------------------------------------------------
            print()
            print("-" * 80)
            print("3. MAPPING FIELDS FOR MAPPING VERSION 2")
            print("-" * 80)

            cursor.execute(
                """
                SELECT
                    mapping_field_id,
                    target_field_id,
                    mapping_type_code,
                    transform_function_id,
                    lookup_id,
                    datatype_mapping_rule_id,
                    transform_expression,
                    expression_language_code,
                    null_rule_code,
                    default_value,
                    key_role_code,
                    scd_behavior_code,
                    ordinal_no
                FROM map.mapping_field
                WHERE mapping_version_id = %s
                ORDER BY ordinal_no;
                """,
                (2,),
            )

            mapping_rows = cursor.fetchall()

            for row in mapping_rows:
                print(row)

            print(
                f"Rows found: {len(mapping_rows)}"
            )

    # -------------------------------------------------------------
    # Final status.
    # -------------------------------------------------------------
    print()
    print("=" * 80)
    print("MAPPING INPUT METADATA INSPECTION COMPLETED")
    print("=" * 80)
    print()
    print(
        "Next we will identify the exact source-field-to-mapping "
        "relationship from the metadata model."
    )


if __name__ == "__main__":
    main()