"""
Inspect Target Configuration Table
===================================

This script reads the actual PostgreSQL structure of
ingest.target_config.

WHY THIS SCRIPT EXISTS
----------------------
Before writing INSERT or UPDATE logic against a metadata table,
we should verify the real database schema instead of assuming
column names.

This prevents errors such as:

    column "database_name" does not exist

The output will show:
    - column names
    - PostgreSQL data types
    - nullable status
    - default values
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the actual columns of ingest.target_config and
    a sample of the existing target metadata.
    """

    print("=" * 80)
    print("INSPECT INGEST.TARGET_CONFIG")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # --------------------------------------------------------------
            # Read the actual table definition from PostgreSQL metadata.
            #
            # information_schema is used here because it provides a
            # database-independent way to inspect table columns.
            # --------------------------------------------------------------
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
                  AND table_name = 'target_config'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            print()
            print("TARGET_CONFIG COLUMNS")
            print("-" * 80)

            if not columns:
                raise RuntimeError(
                    "Table ingest.target_config was not found."
                )

            for (
                ordinal_position,
                column_name,
                data_type,
                is_nullable,
                column_default,
            ) in columns:
                print(
                    f"{ordinal_position:>3} | "
                    f"{column_name:<30} | "
                    f"{data_type:<25} | "
                    f"Nullable={is_nullable:<3} | "
                    f"Default={column_default}"
                )

            # --------------------------------------------------------------
            # Read the current target configuration.
            #
            # We deliberately use SELECT * here because we first want
            # to understand the actual table structure.
            # --------------------------------------------------------------
            cursor.execute(
                """
                SELECT *
                FROM ingest.target_config
                ORDER BY target_id;
                """
            )

            rows = cursor.fetchall()

            print()
            print("CURRENT TARGET CONFIGURATION")
            print("-" * 80)

            for row in rows:
                print(row)

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()