"""
Verify Load Configuration Foreign Key State

Purpose
-------
Confirm the actual PostgreSQL foreign-key state after the previous
migration attempt failed and rolled back.

Why
---
The migration successfully executed:

    DROP old FK
    ADD new FK

inside a transaction.

However, the verification query failed, causing:

    ROLLBACK

Therefore, we need to prove the database returned to its original state.

This script is READ ONLY.

It does not:
    - INSERT
    - UPDATE
    - DELETE
    - ALTER
    - DROP
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Inspect the current foreign keys on ingest.load_config.
    """

    print("=" * 100)
    print("LOAD CONFIG FOREIGN KEY STATE VERIFICATION")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Read PostgreSQL's actual constraint definition.
        #
        # Why:
        # pg_constraint is PostgreSQL's authoritative system catalog for
        # foreign-key constraints.
        # ------------------------------------------------------------------
        print()
        print("=" * 100)
        print("POSTGRESQL FOREIGN KEY DEFINITIONS")
        print("=" * 100)

        query = """
            SELECT
                con.conname AS constraint_name,
                source_ns.nspname AS source_schema,
                source_table.relname AS source_table,
                source_column.attname AS source_column,
                target_ns.nspname AS target_schema,
                target_table.relname AS target_table,
                target_column.attname AS target_column,
                pg_get_constraintdef(con.oid) AS constraint_definition
            FROM pg_constraint con
            JOIN pg_class source_table
                ON source_table.oid = con.conrelid
            JOIN pg_namespace source_ns
                ON source_ns.oid = source_table.relnamespace
            JOIN pg_class target_table
                ON target_table.oid = con.confrelid
            JOIN pg_namespace target_ns
                ON target_ns.oid = target_table.relnamespace
            JOIN LATERAL unnest(con.conkey)
                WITH ORDINALITY AS source_keys(attnum, ordinal_position)
                ON TRUE
            JOIN LATERAL unnest(con.confkey)
                WITH ORDINALITY AS target_keys(attnum, ordinal_position)
                ON target_keys.ordinal_position =
                   source_keys.ordinal_position
            JOIN pg_attribute source_column
                ON source_column.attrelid = source_table.oid
               AND source_column.attnum = source_keys.attnum
            JOIN pg_attribute target_column
                ON target_column.attrelid = target_table.oid
               AND target_column.attnum = target_keys.attnum
            WHERE con.contype = 'f'
              AND source_ns.nspname = 'ingest'
              AND source_table.relname = 'load_config'
            ORDER BY con.conname, source_keys.ordinal_position;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)

            columns = [
                description.name
                for description in cursor.description
            ]

            print(" | ".join(columns))

            rows = cursor.fetchall()

            if not rows:
                print("(NO FOREIGN KEYS FOUND)")
            else:
                for row in rows:
                    print(row)

        # ------------------------------------------------------------------
        # 2. Check specifically for the original legacy FK.
        #
        # Why:
        # The previous migration rolled back, so this constraint should
        # have been restored.
        # ------------------------------------------------------------------
        print()
        print("=" * 100)
        print("EXPECTED LEGACY CONSTRAINT CHECK")
        print("=" * 100)

        legacy_query = """
            SELECT
                conname,
                pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'fk_load_mapping_version'
              AND conrelid = 'ingest.load_config'::regclass;
        """

        with connection.cursor() as cursor:
            cursor.execute(legacy_query)
            row = cursor.fetchone()

        if row is None:
            print(
                "Legacy constraint fk_load_mapping_version: NOT FOUND"
            )
        else:
            print(
                "Legacy constraint fk_load_mapping_version: FOUND"
            )
            print(
                f"Definition: {row[1]}"
            )

        # ------------------------------------------------------------------
        # 3. Check specifically for the new constraint.
        #
        # Why:
        # Because the migration rolled back, this constraint should NOT
        # exist after the transaction rollback.
        # ------------------------------------------------------------------
        print()
        print("=" * 100)
        print("EXPECTED NEW CONSTRAINT CHECK")
        print("=" * 100)

        new_query = """
            SELECT
                conname,
                pg_get_constraintdef(oid)
            FROM pg_constraint
            WHERE conname = 'fk_load_config_mapping_version'
              AND conrelid = 'ingest.load_config'::regclass;
        """

        with connection.cursor() as cursor:
            cursor.execute(new_query)
            row = cursor.fetchone()

        if row is None:
            print(
                "New constraint fk_load_config_mapping_version: NOT FOUND"
            )
        else:
            print(
                "New constraint fk_load_config_mapping_version: FOUND"
            )
            print(
                f"Definition: {row[1]}"
            )

    print()
    print("=" * 100)
    print("FOREIGN KEY STATE VERIFICATION COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    """
    Execute the verification when the module is run directly.
    """

    main()