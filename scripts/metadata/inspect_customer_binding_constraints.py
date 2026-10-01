"""
Customer Dataset Binding Constraint Inspection
================================================

Purpose:
    Inspect the database definition of catalog.dataset_binding before
    creating the physical binding for CUSTOMER_DATASET.

Confirmed metadata:
    Dataset ID       : 7
    Tenant ID        : 1
    Project ID       : 1
    Environment ID   : 1
    Source Connection: 1

Physical source:
    Database         : demo_source_db
    Schema           : public
    Object           : customer

Why this is required:
    catalog.dataset_binding connects the logical dataset in catalog.dataset
    to the actual physical source object.

    Before inserting the binding, we inspect:
        - required columns
        - defaults
        - constraints
        - foreign keys
        - existing bindings

Important:
    This script is READ-ONLY.
    No INSERT, UPDATE, or DELETE operation is performed.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


def print_rows(
    title: str,
    columns: list[str],
    rows: list[tuple],
) -> None:
    """
    Print query results in a consistent tabular format.

    A helper is used so all inspection sections have the same readable
    output format.
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


def main() -> None:
    """
    Inspect catalog.dataset_binding before creating the Customer binding.
    """

    print("=" * 110)
    print("CUSTOMER DATASET BINDING CONSTRAINT INSPECTION")
    print("=" * 110)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Inspect binding table columns
        # ------------------------------------------------------------------
        # This tells us which columns are mandatory and which values are
        # generated automatically by PostgreSQL.
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
                    "catalog",
                    "dataset_binding",
                ),
            )

            column_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET_BINDING COLUMNS",
            [
                "ordinal_position",
                "column_name",
                "data_type",
                "udt_name",
                "is_nullable",
                "column_default",
            ],
            column_rows,
        )

        # ------------------------------------------------------------------
        # 2. Inspect table constraints
        # ------------------------------------------------------------------
        # This identifies primary-key, unique, check, and foreign-key
        # constraints defined for dataset_binding.
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
                    "catalog",
                    "dataset_binding",
                ),
            )

            constraint_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET_BINDING CONSTRAINTS",
            [
                "constraint_name",
                "constraint_type",
                "column_name",
            ],
            constraint_rows,
        )

        # ------------------------------------------------------------------
        # 3. Inspect foreign-key relationships
        # ------------------------------------------------------------------
        # These relationships tell us which metadata records must exist
        # before the physical binding can be created.
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
                    "catalog",
                    "dataset_binding",
                ),
            )

            foreign_key_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET_BINDING FOREIGN KEYS",
            [
                "constraint_name",
                "column_name",
                "referenced_schema",
                "referenced_table",
                "referenced_column",
            ],
            foreign_key_rows,
        )

        # ------------------------------------------------------------------
        # 4. Inspect existing bindings
        # ------------------------------------------------------------------
        # We need to ensure the same physical object is not already bound
        # to this dataset/environment/connection combination.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_binding_id,
                    tenant_id,
                    dataset_id,
                    environment_id,
                    connection_id,
                    catalog_name,
                    schema_name,
                    object_name,
                    object_name_normalized,
                    status_code
                FROM catalog.dataset_binding
                ORDER BY
                    tenant_id,
                    dataset_id,
                    dataset_binding_id;
                """
            )

            binding_rows = cursor.fetchall()

        print_rows(
            "EXISTING CATALOG.DATASET_BINDING RECORDS",
            [
                "dataset_binding_id",
                "tenant_id",
                "dataset_id",
                "environment_id",
                "connection_id",
                "catalog_name",
                "schema_name",
                "object_name",
                "object_name_normalized",
                "status_code",
            ],
            binding_rows,
        )

    # ----------------------------------------------------------------------
    # Completion
    # ----------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("INSPECTION COMPLETE")
    print("=" * 110)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Execute the inspection when this module is run directly.
    main()