"""
Inspect Dataset Binding Structure
=================================

Purpose
-------
Inspect the actual deployed structure of:

    catalog.dataset_binding

Why
---
The runtime object resolver assumed that physical database information was
stored in columns such as:

    database_name
    schema_name
    object_name

PostgreSQL reported that database_name does not exist.

Instead of guessing the schema, this script reads the actual metadata
definition and the Customer source/target binding rows.

This script is READ ONLY.

It does not:
    - insert data
    - update metadata
    - delete metadata
    - connect to source databases
    - connect to target databases
"""

# Import the application's centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# Dataset IDs already established for the Customer POC.
SOURCE_DATASET_ID = 7
TARGET_DATASET_ID = 8


def inspect_dataset_binding_structure() -> None:
    """
    Display the actual catalog.dataset_binding structure and the
    active bindings for Customer source and target datasets.
    """

    print("=" * 100)
    print("CATALOG.DATASET_BINDING STRUCTURE")
    print("=" * 100)

    # Open the metadata/control database connection.
    with get_metastore_connection() as connection:

        # Create a cursor for read-only metadata queries.
        with connection.cursor() as cursor:

            # ------------------------------------------------------------------
            # 1. Inspect actual dataset_binding columns
            # ------------------------------------------------------------------
            # information_schema is the authoritative source for the currently
            # deployed table structure.
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'catalog'
                  AND table_name = 'dataset_binding'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            if not columns:
                raise RuntimeError(
                    "Table catalog.dataset_binding was not found."
                )

            print()
            print(
                "ordinal_position | column_name | data_type | "
                "nullable | default"
            )
            print("-" * 100)

            # Display every physical column in the table.
            for row in columns:
                print(row)

            # ------------------------------------------------------------------
            # 2. Inspect dataset_binding constraints
            # ------------------------------------------------------------------
            # This tells us how dataset_binding relates to dataset,
            # connection metadata, tenant, and other catalog objects.
            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_schema AS referenced_schema,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column
                FROM information_schema.table_constraints AS tc
                LEFT JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                   AND tc.table_name = kcu.table_name
                LEFT JOIN information_schema.constraint_column_usage AS ccu
                    ON tc.constraint_name = ccu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                WHERE tc.table_schema = 'catalog'
                  AND tc.table_name = 'dataset_binding'
                ORDER BY
                    tc.constraint_type,
                    tc.constraint_name,
                    kcu.ordinal_position;
                """
            )

            constraints = cursor.fetchall()

            print()
            print("=" * 100)
            print("DATASET BINDING CONSTRAINTS")
            print("=" * 100)

            if not constraints:
                print("No constraints found.")
            else:
                print(
                    "constraint_name | constraint_type | column | "
                    "referenced_schema | referenced_table | referenced_column"
                )
                print("-" * 100)

                # Display the actual constraints defined in PostgreSQL.
                for row in constraints:
                    print(row)

            # ------------------------------------------------------------------
            # 3. Read source and target binding rows
            # ------------------------------------------------------------------
            # We use SELECT * because the actual column names are still being
            # discovered. This prevents another incorrect column assumption.
            cursor.execute(
                """
                SELECT *
                FROM catalog.dataset_binding
                WHERE dataset_id IN (%s, %s)
                ORDER BY dataset_id, dataset_binding_id;
                """,
                (
                    SOURCE_DATASET_ID,
                    TARGET_DATASET_ID,
                ),
            )

            binding_rows = cursor.fetchall()

            if not binding_rows:
                raise RuntimeError(
                    "No dataset bindings were found for Customer "
                    f"datasets {SOURCE_DATASET_ID} and {TARGET_DATASET_ID}."
                )

            print()
            print("=" * 100)
            print("CUSTOMER DATASET BINDINGS")
            print("=" * 100)

            # Extract actual column names from the table structure.
            column_names = [column[1] for column in columns]

            # Display each binding using its actual database column names.
            for row in binding_rows:

                print()
                print("-" * 100)

                for column_name, value in zip(column_names, row):
                    print(f"{column_name:<40} : {value}")

            print()
            print("=" * 100)
            print("INSPECTION COMPLETED")
            print("=" * 100)
            print("Operation         : READ ONLY")
            print("Metadata modified : NO")
            print("=" * 100)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
# Allows execution using Python module syntax.
if __name__ == "__main__":
    inspect_dataset_binding_structure()