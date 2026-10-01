"""
Customer Schema Capture Constraint Inspection
===============================================

Purpose:
    Inspect the database structures required to persist a dynamically
    discovered Customer source schema.

Metadata tables involved:

    1. catalog.schema_capture_run
       --------------------------------
       Records the execution of a schema discovery operation.

    2. catalog.dataset_schema_version
       --------------------------------
       Stores the immutable version of the discovered dataset schema.

    3. catalog.dataset_field
       --------------------------------
       Stores the individual fields/columns belonging to that schema
       version.

Confirmed Customer metadata:

    Tenant ID        : 1
    Project ID       : 1
    Environment ID   : 1
    Dataset ID       : 7
    Binding ID       : 7
    Source Connection: 1

Physical source:

    demo_source_db.public.customer

Expected source fields currently known from previous connector discovery:

    customer_id
    customer_name
    email
    city

Important:
    This script is READ-ONLY.

    It does not create schema-capture records or modify metadata.
"""


from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Utility function
# ---------------------------------------------------------------------------
# This helper keeps the output formatting consistent across all inspection
# sections and makes the main function easier to read.
def print_rows(
    title: str,
    columns: list[str],
    rows: list[tuple],
) -> None:
    """
    Print database query results in a readable tabular format.
    """

    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)

    if not rows:
        print("No rows returned.")
        return

    print(" | ".join(columns))
    print("-" * 110)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    print(f"\nRows returned: {len(rows)}")


# ---------------------------------------------------------------------------
# Table inspection function
# ---------------------------------------------------------------------------
# We inspect one metadata table at a time so that each table's structure is
# clearly visible before we implement the write operation.
def inspect_table(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect columns, constraints, and foreign keys for one metadata table.
    """

    # -----------------------------------------------------------------------
    # Columns
    # -----------------------------------------------------------------------
    # information_schema tells us which columns are mandatory, their data
    # types, and whether PostgreSQL provides a default value.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                ordinal_position,
                column_name,
                data_type,
                udt_name,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position;
            """,
            (
                schema_name,
                table_name,
            ),
        )

        rows = cursor.fetchall()

    print_rows(
        f"{schema_name.upper()}.{table_name.upper()} COLUMNS",
        [
            "ordinal_position",
            "column_name",
            "data_type",
            "udt_name",
            "is_nullable",
            "column_default",
        ],
        rows,
    )

    # -----------------------------------------------------------------------
    # Constraints
    # -----------------------------------------------------------------------
    # Constraints reveal primary keys, uniqueness requirements, checks, and
    # foreign-key relationships that the insertion logic must respect.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name
            FROM information_schema.table_constraints AS tc
            LEFT JOIN information_schema.key_column_usage AS kcu
                ON kcu.constraint_schema = tc.constraint_schema
               AND kcu.constraint_name = tc.constraint_name
               AND kcu.table_name = tc.table_name
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY
                tc.constraint_name,
                kcu.ordinal_position;
            """,
            (
                schema_name,
                table_name,
            ),
        )

        rows = cursor.fetchall()

    print_rows(
        f"{schema_name.upper()}.{table_name.upper()} CONSTRAINTS",
        [
            "constraint_name",
            "constraint_type",
            "column_name",
        ],
        rows,
    )

    # -----------------------------------------------------------------------
    # Foreign keys
    # -----------------------------------------------------------------------
    # This identifies the parent metadata records that must already exist
    # before a schema-capture record can be persisted.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_schema AS referenced_schema,
                ccu.table_name AS referenced_table,
                ccu.column_name AS referenced_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON kcu.constraint_schema = tc.constraint_schema
               AND kcu.constraint_name = tc.constraint_name
               AND kcu.table_name = tc.table_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_schema = tc.constraint_schema
               AND ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = %s
              AND tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY tc.constraint_name;
            """,
            (
                "FOREIGN KEY",
                schema_name,
                table_name,
            ),
        )

        rows = cursor.fetchall()

    print_rows(
        f"{schema_name.upper()}.{table_name.upper()} FOREIGN KEYS",
        [
            "constraint_name",
            "column_name",
            "referenced_schema",
            "referenced_table",
            "referenced_column",
        ],
        rows,
    )


def main() -> None:
    """
    Inspect all metadata tables required for Customer schema capture.
    """

    print("=" * 110)
    print("CUSTOMER SCHEMA CAPTURE CONSTRAINT INSPECTION")
    print("=" * 110)

    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # 1. Inspect schema_capture_run
        # -------------------------------------------------------------------
        # This table represents the execution/evidence of the discovery
        # operation itself.
        inspect_table(
            connection,
            "catalog",
            "schema_capture_run",
        )

        # -------------------------------------------------------------------
        # 2. Inspect dataset_schema_version
        # -------------------------------------------------------------------
        # This table stores the resulting immutable schema snapshot.
        inspect_table(
            connection,
            "catalog",
            "dataset_schema_version",
        )

        # -------------------------------------------------------------------
        # 3. Inspect dataset_field
        # -------------------------------------------------------------------
        # This table stores each discovered source column and its datatype
        # information.
        inspect_table(
            connection,
            "catalog",
            "dataset_field",
        )

        # -------------------------------------------------------------------
        # 4. Check existing Customer schema metadata
        # -------------------------------------------------------------------
        # Before creating a new capture, check whether the Customer dataset
        # already has schema versions or fields in our Tenant 1 / Dataset 7
        # context.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    schema_version_id,
                    dataset_id,
                    source_binding_id,
                    schema_capture_run_id,
                    version_no,
                    schema_hash,
                    source_code,
                    change_type_code,
                    captured_at,
                    is_current
                FROM catalog.dataset_schema_version
                WHERE dataset_id = %s
                ORDER BY version_no;
                """,
                (7,),
            )

            schema_version_rows = cursor.fetchall()

        print_rows(
            "EXISTING CUSTOMER SCHEMA VERSIONS",
            [
                "schema_version_id",
                "dataset_id",
                "source_binding_id",
                "schema_capture_run_id",
                "version_no",
                "schema_hash",
                "source_code",
                "change_type_code",
                "captured_at",
                "is_current",
            ],
            schema_version_rows,
        )

        # -------------------------------------------------------------------
        # 5. Check existing Customer fields
        # -------------------------------------------------------------------
       # dataset_field does not contain a status_code column.
        #
        # Its lifecycle information is represented through the parent
        # schema_version and the field-level metadata itself. Therefore,
        # the query below selects only columns that actually exist in
        # catalog.dataset_field.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    field_id,
                    schema_version_id,
                    ordinal_no,
                    field_name,
                    field_name_normalized,
                    native_datatype_id,
                    source_datatype_text,
                    length_value,
                    precision_value,
                    scale_value,
                    is_nullable,
                    default_expression,
                    is_identity,
                    is_generated,
                    classification_id,
                    description
                FROM catalog.dataset_field
                WHERE schema_version_id IN
                (
                    SELECT
                        schema_version_id
                    FROM catalog.dataset_schema_version
                    WHERE dataset_id = %s
                )
                ORDER BY
                    schema_version_id,
                    ordinal_no;
                """,
                (7,),
            )

            field_rows = cursor.fetchall()

        print_rows(
            "EXISTING CUSTOMER SCHEMA FIELDS",
            [
                 "field_id",
                "schema_version_id",
                "ordinal_no",
                "field_name",
                "field_name_normalized",
                "native_datatype_id",
                "source_datatype_text",
                "length_value",
                "precision_value",
                "scale_value",
                "is_nullable",
                "default_expression",
                "is_identity",
                "is_generated",
                "classification_id",
                "description",
            ],
            field_rows,
        )

    print("\n" + "=" * 110)
    print("INSPECTION COMPLETE")
    print("=" * 110)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Execute the read-only inspection when this module is run directly.
    main()