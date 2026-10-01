"""
Customer Source Field Metadata Inspection
==========================================

Purpose
-------
Inspect the metadata tables that may contain the physical source
fields for Customer Source Schema Version 6.

WHY:
----
Mapping Version 2 references:

    Source Dataset       = 7
    Source Schema Version = 6

Before implementing the Full Load Executor, we must know exactly
how the platform resolves:

    schema_version_id
            |
            v
    source fields
            |
            v
    physical column names

IMPORTANT:
----------
This script is READ-ONLY.

It only inspects metadata and does not insert, update, delete,
or modify any database records.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect candidate metadata tables for source schema version 6.
    """

    # -------------------------------------------------------------
    # Display a clear heading so the purpose of the script is
    # immediately visible in the terminal.
    # -------------------------------------------------------------
    print("=" * 80)
    print("CUSTOMER SOURCE FIELD METADATA - SCHEMA VERSION 6")
    print("=" * 80)

    # -------------------------------------------------------------
    # Open a connection to the metadata store.
    #
    # The connection manager does not auto-commit, and this script
    # performs only SELECT operations.
    # -------------------------------------------------------------
    with get_metastore_connection() as connection:

        # ---------------------------------------------------------
        # Create a cursor for executing metadata queries.
        # ---------------------------------------------------------
        with connection.cursor() as cursor:

            # =====================================================
            # 1. Inspect catalog.dataset_field
            # =====================================================
            #
            # This table is especially important because the
            # previous inspection confirmed that it contains both:
            #
            #     field_id
            #     schema_version_id
            #
            # Therefore it is a strong candidate for resolving
            # source fields.
            # =====================================================
            print()
            print("-" * 80)
            print("1. catalog.dataset_field")
            print("-" * 80)

            cursor.execute(
                """
                SELECT *
                FROM catalog.dataset_field
                WHERE schema_version_id = %s
                ORDER BY field_id;
                """,
                (6,),
            )

            dataset_field_rows = cursor.fetchall()

            # Display the returned rows.
            for row in dataset_field_rows:
                print(row)

            print(f"Rows found: {len(dataset_field_rows)}")

            # =====================================================
            # 2. Inspect ingest.schema_field
            # =====================================================
            #
            # This table also contains schema_version_id.
            #
            # We need to determine whether it represents:
            #
            #     source physical fields
            #
            # or some other ingestion-specific field metadata.
            # =====================================================
            print()
            print("-" * 80)
            print("2. ingest.schema_field")
            print("-" * 80)

            cursor.execute(
                """
                SELECT *
                FROM ingest.schema_field
                WHERE schema_version_id = %s
                ORDER BY 1;
                """,
                (6,),
            )

            schema_field_rows = cursor.fetchall()

            # Display the returned rows.
            for row in schema_field_rows:
                print(row)

            print(f"Rows found: {len(schema_field_rows)}")

            # =====================================================
            # 3. Inspect catalog.dataset_schema_version
            # =====================================================
            #
            # This allows us to see the metadata associated with
            # schema_version_id = 6 and understand how the schema
            # version connects to the dataset.
            # =====================================================
            print()
            print("-" * 80)
            print("3. catalog.dataset_schema_version")
            print("-" * 80)

            cursor.execute(
                """
                SELECT *
                FROM catalog.dataset_schema_version
                WHERE schema_version_id = %s;
                """,
                (6,),
            )

            schema_version_rows = cursor.fetchall()

            # Display the schema-version metadata.
            for row in schema_version_rows:
                print(row)

            print(f"Rows found: {len(schema_version_rows)}")

    # -------------------------------------------------------------
    # Final message.
    # -------------------------------------------------------------
    print()
    print("=" * 80)
    print("SOURCE FIELD METADATA INSPECTION COMPLETED")
    print("=" * 80)
    print()
    print(
        "Next we will identify the authoritative source-field table "
        "and its relationship to mapping_field."
    )


# -------------------------------------------------------------
# Python module entry point.
# -------------------------------------------------------------
if __name__ == "__main__":
    main()