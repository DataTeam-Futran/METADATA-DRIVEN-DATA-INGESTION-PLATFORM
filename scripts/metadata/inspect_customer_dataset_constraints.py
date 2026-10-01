"""
Customer Dataset Constraint Inspection
=======================================

Purpose:
    Inspect the database definition of catalog.dataset before creating the
    first Customer dataset metadata record.

Why this is required:
    catalog.dataset contains several metadata and audit columns. Some may
    have defaults, NOT NULL constraints, foreign keys, or controlled values.

    We should inspect the actual database definition instead of guessing
    which values can be inserted.

Confirmed POC context:
    Tenant      : 1
    Project     : 1
    Environment : 1
    Source      : Connection 1
    Target      : Connection 11

Important:
    This script is completely READ-ONLY.
    No INSERT, UPDATE, or DELETE operation is performed.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


def print_rows(title: str, columns: list[str], rows: list[tuple]) -> None:
    """
    Print query results in a readable tabular format.

    Keeping output formatting in one helper makes the main inspection logic
    easier to follow.
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
    Inspect catalog.dataset columns, constraints, and foreign keys.

    The information returned by this script will be used to construct the
    first safe INSERT for CUSTOMER_DATASET.
    """

    print("=" * 110)
    print("CUSTOMER DATASET CONSTRAINT INSPECTION")
    print("=" * 110)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Inspect columns
        # ------------------------------------------------------------------
        # information_schema provides the actual database column definition,
        # including data type, nullability, and default expressions.
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
                ("catalog", "dataset"),
            )

            column_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET COLUMNS",
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
        # This identifies PRIMARY KEY, UNIQUE, CHECK, and FOREIGN KEY
        # constraints defined directly on catalog.dataset.
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
                ("catalog", "dataset"),
            )

            constraint_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET CONSTRAINTS",
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
        # Foreign keys tell us which parent metadata records must already
        # exist before catalog.dataset can be inserted.
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
                    "dataset",
                ),
            )

            foreign_key_rows = cursor.fetchall()

        print_rows(
            "CATALOG.DATASET FOREIGN KEYS",
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
        # 4. Inspect existing dataset codes
        # ------------------------------------------------------------------
        # This provides a final view of currently registered dataset codes.
        # It is useful before creating a new stable metadata identifier.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_id,
                    tenant_id,
                    project_id,
                    dataset_code,
                    dataset_name,
                    object_type_code,
                    dataset_role_code,
                    layer_code,
                    status_code
                FROM catalog.dataset
                ORDER BY tenant_id, project_id, dataset_id;
                """
            )

            existing_rows = cursor.fetchall()

        print_rows(
            "EXISTING CATALOG.DATASET RECORDS",
            [
                "dataset_id",
                "tenant_id",
                "project_id",
                "dataset_code",
                "dataset_name",
                "object_type_code",
                "dataset_role_code",
                "layer_code",
                "status_code",
            ],
            existing_rows,
        )

    # ----------------------------------------------------------------------
    # Completion
    # ----------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("INSPECTION COMPLETE")
    print("=" * 110)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Run the inspection when this file is executed as a Python module.
    main()