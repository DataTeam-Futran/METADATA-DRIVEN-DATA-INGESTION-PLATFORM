"""
Inspect Mapping Version
=======================

This script reads the actual PostgreSQL definition of:

    ingest.mapping_version

WHY THIS SCRIPT EXISTS
----------------------
The POC execution-chain inspection should be based on the actual
metadata schema.

We previously assumed a version-number column name, but PostgreSQL
has shown that those assumptions were incorrect.

Therefore this script first retrieves the real column names.

IMPORTANT
---------
This script is READ-ONLY.

It does not INSERT, UPDATE, DELETE, or ALTER any metadata.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the actual columns and rows of ingest.mapping_version.
    """

    print("=" * 80)
    print("INSPECT INGEST.MAPPING_VERSION")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # ----------------------------------------------------------------
            # STEP 1
            #
            # Read the actual table definition from PostgreSQL.
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
                  AND table_name = 'mapping_version'
                ORDER BY ordinal_position;
                """
            )

            columns = cursor.fetchall()

            if not columns:
                raise RuntimeError(
                    "Table ingest.mapping_version was not found."
                )

            print()
            print("MAPPING_VERSION COLUMNS")
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
            # Display the existing rows.
            #
            # SELECT * is intentional because we are inspecting the real
            # schema rather than assuming column names.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT *
                FROM ingest.mapping_version
                ORDER BY mapping_version_id;
                """
            )

            rows = cursor.fetchall()

            print()
            print("CURRENT MAPPING VERSION DATA")
            print("-" * 80)

            if not rows:
                print("No mapping version records found.")

            else:
                for row in rows:
                    print(row)

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()