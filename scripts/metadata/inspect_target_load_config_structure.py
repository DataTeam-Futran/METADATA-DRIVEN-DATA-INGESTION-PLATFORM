"""
Inspect Target Load Configuration Structure
============================================

Purpose
-------
Inspect the actual structure of:

    ingest.target_load_config

Why
---
The orchestration verification script currently assumes that columns such as
alter_policy_code exist.

PostgreSQL reported that alter_policy_code does not exist.

Instead of guessing the schema, this script reads the actual database
metadata and displays the columns and Customer mapping configuration.

This script is READ ONLY.
It does not insert, update, or delete anything.
"""

# Import the application's centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# Customer mapping version created earlier in the development process.
EXPECTED_MAPPING_VERSION_ID = 2


def inspect_target_load_config_structure() -> None:
    """
    Display the actual target_load_config table structure and
    the configuration for Customer mapping version 2.
    """

    print("=" * 100)
    print("INGEST.TARGET_LOAD_CONFIG STRUCTURE")
    print("=" * 100)

    # Open the metadata/control database connection.
    with get_metastore_connection() as connection:

        # Create a cursor for read-only metadata queries.
        with connection.cursor() as cursor:

            # ------------------------------------------------------------------
            # 1. Inspect actual table columns
            # ------------------------------------------------------------------
            # information_schema provides the authoritative column definition
            # currently deployed in PostgreSQL.
            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'ingest'
                  AND table_name = 'target_load_config'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            if not columns:
                raise RuntimeError(
                    "Table ingest.target_load_config was not found."
                )

            print()
            print(
                "ordinal_position | column_name | data_type | "
                "nullable | default"
            )
            print("-" * 100)

            # Print every actual column in the table.
            for row in columns:
                print(row)

            # ------------------------------------------------------------------
            # 2. Inspect constraints
            # ------------------------------------------------------------------
            # Constraints help us understand how target_load_config is linked
            # to mapping_version and tenant metadata.
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
                WHERE tc.table_schema = 'ingest'
                  AND tc.table_name = 'target_load_config'
                ORDER BY
                    tc.constraint_type,
                    tc.constraint_name,
                    kcu.ordinal_position;
                """
            )

            constraints = cursor.fetchall()

            print()
            print("=" * 100)
            print("TARGET LOAD CONFIGURATION CONSTRAINTS")
            print("=" * 100)

            if not constraints:
                print("No constraints found.")
            else:
                print(
                    "constraint_name | constraint_type | column | "
                    "referenced_schema | referenced_table | referenced_column"
                )
                print("-" * 100)

                # Display the actual database constraints.
                for row in constraints:
                    print(row)

            # ------------------------------------------------------------------
            # 3. Read Customer target-load configuration
            # ------------------------------------------------------------------
            # SELECT * is intentionally used here because we first want to
            # discover the exact deployed column layout.
            cursor.execute(
                """
                SELECT *
                FROM ingest.target_load_config
                WHERE mapping_version_id = %s
                ORDER BY mapping_version_id
                LIMIT 1;
                """,
                (EXPECTED_MAPPING_VERSION_ID,),
            )

            target_config = cursor.fetchone()

            if target_config is None:
                raise RuntimeError(
                    "Target load configuration was not found for "
                    f"mapping version {EXPECTED_MAPPING_VERSION_ID}."
                )

            print()
            print("=" * 100)
            print("CUSTOMER TARGET LOAD CONFIGURATION")
            print("=" * 100)

            # Extract actual column names from information_schema.
            column_names = [column[1] for column in columns]

            # Print each actual column with its stored value.
            for column_name, value in zip(column_names, target_config):
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
# Allows execution using Python's module execution syntax.
if __name__ == "__main__":
    inspect_target_load_config_structure()