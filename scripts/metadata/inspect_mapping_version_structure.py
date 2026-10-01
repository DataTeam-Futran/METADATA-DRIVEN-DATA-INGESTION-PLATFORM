"""
Inspect Mapping Version Table Structure
========================================

Purpose
-------
Inspect the actual columns and constraints of:

    map.mapping_version

Why
---
The orchestration verification script assumed that columns such as
source_dataset_id and target_dataset_id exist directly in
map.mapping_version.

PostgreSQL reported that source_dataset_id does not exist.

Instead of guessing the schema, this script reads the actual database
metadata and shows the columns that really exist.

This script is READ ONLY.
It does not insert, update, or delete anything.
"""

# Import the application's centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


def inspect_mapping_version_structure() -> None:
    """
    Read and display the actual map.mapping_version structure.
    """

    print("=" * 100)
    print("MAP.MAPPING_VERSION STRUCTURE")
    print("=" * 100)

    # Open a connection to the metadata/control database.
    with get_metastore_connection() as connection:

        # Create a cursor for read-only metadata queries.
        with connection.cursor() as cursor:

            # ------------------------------------------------------------------
            # 1. Read all columns from map.mapping_version
            # ------------------------------------------------------------------
            # information_schema is used instead of hardcoding the expected
            # column names because the actual database schema is authoritative.
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'map'
                  AND table_name = 'mapping_version'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            if not columns:
                raise RuntimeError(
                    "Table map.mapping_version was not found."
                )

            print()
            print(
                "ordinal_position | column_name | data_type | "
                "nullable | default"
            )
            print("-" * 100)

            # Display every actual column in the table.
            for row in columns:
                print(row)

            # ------------------------------------------------------------------
            # 2. Read primary key / unique / foreign-key constraints
            # ------------------------------------------------------------------
            # Constraints help us understand how mapping_version connects to
            # mapping, datasets, schema versions, and other metadata objects.
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
                   AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = 'map'
                  AND tc.table_name = 'mapping_version'
                ORDER BY
                    tc.constraint_type,
                    tc.constraint_name,
                    kcu.ordinal_position;
                """
            )

            constraints = cursor.fetchall()

            print()
            print("=" * 100)
            print("MAP.MAPPING_VERSION CONSTRAINTS")
            print("=" * 100)

            if not constraints:
                print("No constraints found.")
            else:
                print(
                    "constraint_name | constraint_type | column | "
                    "referenced_schema | referenced_table | referenced_column"
                )
                print("-" * 100)

                # Display the actual relationships defined by the database.
                for row in constraints:
                    print(row)

            # ------------------------------------------------------------------
            # 3. Read the actual Customer mapping version row
            # ------------------------------------------------------------------
            # This confirms which columns contain values for mapping_version_id=2.
            cursor.execute(
                """
                SELECT *
                FROM map.mapping_version
                WHERE mapping_version_id = %s;
                """,
                (2,),
            )

            mapping_row = cursor.fetchone()

            if mapping_row is None:
                raise RuntimeError(
                    "Mapping version 2 was not found."
                )

            print()
            print("=" * 100)
            print("CUSTOMER MAPPING VERSION 2")
            print("=" * 100)

            # Print the column names followed by their corresponding values.
            column_names = [column[1] for column in columns]

            for column_name, value in zip(column_names, mapping_row):
                print(f"{column_name:<35} : {value}")

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
# Allows the script to be executed as a Python module.
if __name__ == "__main__":
    inspect_mapping_version_structure()