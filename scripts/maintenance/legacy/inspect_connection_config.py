"""
Inspect Connection Config
=========================

This script inspects the connection_config table referenced by
the foreign-key constraint:

    fk_target_connection

on:

    ingest.target_config.connection_id

WHY THIS IS REQUIRED
--------------------
We discovered that ingest.target_config does not directly reference:

    conn.connection_profile

Instead, PostgreSQL reports that it references:

    connection_config

Therefore, before changing any metadata, we need to understand:

    1. Where connection_config is located.
    2. Which columns it contains.
    3. Which record currently represents the existing target connection.
    4. Which foreign keys connect it to the conn schema.

IMPORTANT
---------
This script is READ-ONLY.

It does not insert, update, or delete anything.
"""


from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect the connection_config table and display its structure
    and current records.
    """

    print("=" * 80)
    print("INSPECT CONNECTION_CONFIG")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # ----------------------------------------------------------------
            # STEP 1
            #
            # Find the actual schema containing connection_config.
            #
            # We search all non-system schemas instead of assuming that the
            # table is inside conn.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name
                FROM information_schema.tables
                WHERE table_name = 'connection_config'
                  AND table_schema NOT IN (
                      'pg_catalog',
                      'information_schema'
                  )
                ORDER BY table_schema;
                """
            )

            tables = cursor.fetchall()

            if not tables:
                raise RuntimeError(
                    "No connection_config table was found."
                )

            print()
            print("CONNECTION_CONFIG TABLE")
            print("-" * 80)

            for schema_name, table_name in tables:
                print(
                    f"Schema : {schema_name}"
                )
                print(
                    f"Table  : {table_name}"
                )

            # ----------------------------------------------------------------
            # STEP 2
            #
            # Inspect the columns of every discovered connection_config
            # table.
            # ----------------------------------------------------------------
            for schema_name, table_name in tables:

                print()
                print(
                    f"COLUMNS: {schema_name}.{table_name}"
                )
                print("-" * 80)

                cursor.execute(
                    """
                    SELECT
                        ordinal_position,
                        column_name,
                        data_type,
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

                columns = cursor.fetchall()

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
            # STEP 3
            #
            # Display the existing rows.
            #
            # This is important because the target_config currently points
            # to an existing connection ID, and we need to understand what
            # that ID represents in connection_config.
            # ----------------------------------------------------------------
            for schema_name, table_name in tables:

                print()
                print(
                    f"DATA: {schema_name}.{table_name}"
                )
                print("-" * 80)

                cursor.execute(
                    f"""
                    SELECT *
                    FROM "{schema_name}"."{table_name}"
                    ORDER BY 1;
                    """
                )

                rows = cursor.fetchall()

                if not rows:
                    print("No rows found.")
                else:
                    for row in rows:
                        print(row)

            # ----------------------------------------------------------------
            # STEP 4
            #
            # Inspect the foreign-key relationship from target_config.
            #
            # This tells us exactly which column in connection_config is
            # referenced by ingest.target_config.connection_id.
            # ----------------------------------------------------------------
            print()
            print("TARGET CONNECTION FOREIGN KEY")
            print("-" * 80)

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
                  AND kcu.table_schema = 'ingest'
                  AND kcu.table_name = 'target_config'
                  AND kcu.column_name = 'connection_id';
                """
            )

            foreign_keys = cursor.fetchall()

            for row in foreign_keys:
                print(
                    f"Constraint        : {row[0]}"
                )
                print(
                    f"Source            : "
                    f"{row[1]}.{row[2]}.{row[3]}"
                )
                print(
                    f"Referenced        : "
                    f"{row[4]}.{row[5]}.{row[6]}"
                )

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()