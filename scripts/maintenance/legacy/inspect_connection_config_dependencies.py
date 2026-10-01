"""
Inspect Connection Config Dependencies
======================================

This script identifies all foreign-key relationships involving:

    ingest.connection_config

WHY THIS IS IMPORTANT
---------------------
We discovered that:

    ingest.target_config.connection_id
            |
            v
    ingest.connection_config.connection_id

However, our newer connection architecture uses:

    conn.connection_profile

Before changing the metadata model, we need to know whether
other tables also depend on ingest.connection_config.

This script is READ-ONLY.

It does not modify any metadata.
"""


from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display all foreign-key relationships that reference
    ingest.connection_config.
    """

    print("=" * 80)
    print("INSPECT CONNECTION_CONFIG DEPENDENCIES")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # ----------------------------------------------------------------
            # Find all foreign keys whose referenced table is:
            #
            #     ingest.connection_config
            #
            # This tells us which tables depend on this connection model.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT
                    tc.constraint_name,

                    kcu.table_schema AS source_schema,
                    kcu.table_name AS source_table,
                    kcu.column_name AS source_column,

                    ccu.table_schema AS referenced_schema,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column

                FROM information_schema.table_constraints AS tc

                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema

                JOIN information_schema.constraint_column_usage AS ccu
                    ON tc.constraint_name = ccu.constraint_name
                   AND tc.table_schema = ccu.table_schema

                WHERE tc.constraint_type = 'FOREIGN KEY'

                  AND ccu.table_schema = 'ingest'
                  AND ccu.table_name = 'connection_config'

                ORDER BY
                    source_schema,
                    source_table,
                    source_column;
                """
            )

            dependencies = cursor.fetchall()

            print()
            print("FOREIGN-KEY DEPENDENCIES")
            print("-" * 80)

            if not dependencies:
                print(
                    "No foreign-key dependencies were found."
                )

            else:

                for row in dependencies:

                    (
                        constraint_name,
                        source_schema,
                        source_table,
                        source_column,
                        referenced_schema,
                        referenced_table,
                        referenced_column,
                    ) = row

                    print(
                        f"Constraint : {constraint_name}"
                    )

                    print(
                        f"Source     : "
                        f"{source_schema}.{source_table}"
                        f".{source_column}"
                    )

                    print(
                        f"Referenced : "
                        f"{referenced_schema}.{referenced_table}"
                        f".{referenced_column}"
                    )

                    print("-" * 80)

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()