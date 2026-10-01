"""
Inspect Source Configuration
============================

This script reads the actual PostgreSQL definition of:

    ingest.source_config

WHY THIS SCRIPT EXISTS
----------------------
We are investigating the relationship between:

    ingest.source_config
            |
            v
    ingest.connection_config

and the newer:

    conn.connection_profile

Before writing comparison or migration logic, we must use the
actual column names from the database rather than assuming them.

IMPORTANT
---------
This script is READ-ONLY.

It does not INSERT, UPDATE, DELETE, or ALTER anything.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the actual columns and current rows of
    ingest.source_config.
    """

    print("=" * 80)
    print("INSPECT INGEST.SOURCE_CONFIG")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # ----------------------------------------------------------------
            # STEP 1
            #
            # Read the actual column definition from PostgreSQL.
            #
            # information_schema.columns tells us the real column names,
            # data types, nullable status, and defaults.
            # ----------------------------------------------------------------
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
                  AND table_name = 'source_config'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            if not columns:
                raise RuntimeError(
                    "Table ingest.source_config was not found."
                )

            print()
            print("SOURCE_CONFIG COLUMNS")
            print("-" * 80)

            for (
                ordinal_position,
                column_name,
                data_type,
                is_nullable,
                column_default,
            ) in columns:

                print(
                    f"{ordinal_position:>3} | "
                    f"{column_name:<35} | "
                    f"{data_type:<25} | "
                    f"Nullable={is_nullable:<3} | "
                    f"Default={column_default}"
                )

            # ----------------------------------------------------------------
            # STEP 2
            #
            # Read the existing source configuration.
            #
            # SELECT * is intentional here because we are inspecting the
            # real structure before writing any query that depends on
            # specific column names.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT *
                FROM ingest.source_config
                ORDER BY source_id;
                """
            )

            rows = cursor.fetchall()

            print()
            print("CURRENT SOURCE CONFIGURATION")
            print("-" * 80)

            if not rows:
                print("No source configuration records found.")

            else:
                for row in rows:
                    print(row)

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()