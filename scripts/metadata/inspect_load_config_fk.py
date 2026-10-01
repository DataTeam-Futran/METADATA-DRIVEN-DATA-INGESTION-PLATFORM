"""
Inspect the foreign-key relationship of ingest.load_config.

Purpose:
    Determine exactly which table and column the
    fk_load_mapping_version constraint references.

Why:
    The Customer mapping exists in map.mapping_version with ID 2,
    but PostgreSQL rejected that ID when inserting into
    ingest.load_config.

This script does not modify any metadata.
"""

from app.db.metastore import get_metastore_connection


def inspect_load_config_fk(connection) -> None:
    """
    Read the PostgreSQL system catalog to resolve the exact FK target.

    Why:
        Looking only at the FK constraint name is not sufficient.
        We need the actual referenced schema, table and column.
    """

    query = """
        SELECT
            con.conname AS constraint_name,
            source_ns.nspname AS source_schema,
            source_tbl.relname AS source_table,
            source_col.attname AS source_column,
            target_ns.nspname AS target_schema,
            target_tbl.relname AS target_table,
            target_col.attname AS target_column,
            pg_get_constraintdef(con.oid) AS constraint_definition
        FROM pg_constraint con
        JOIN pg_class source_tbl
            ON source_tbl.oid = con.conrelid
        JOIN pg_namespace source_ns
            ON source_ns.oid = source_tbl.relnamespace
        JOIN pg_class target_tbl
            ON target_tbl.oid = con.confrelid
        JOIN pg_namespace target_ns
            ON target_ns.oid = target_tbl.relnamespace
        JOIN LATERAL unnest(con.conkey)
            WITH ORDINALITY AS source_keys(attnum, ordinal)
            ON TRUE
        JOIN LATERAL unnest(con.confkey)
            WITH ORDINALITY AS target_keys(attnum, ordinal)
            ON target_keys.ordinal = source_keys.ordinal
        JOIN pg_attribute source_col
            ON source_col.attrelid = source_tbl.oid
           AND source_col.attnum = source_keys.attnum
        JOIN pg_attribute target_col
            ON target_col.attrelid = target_tbl.oid
           AND target_col.attnum = target_keys.attnum
        WHERE con.conname = 'fk_load_mapping_version';
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print("=" * 100)
    print("LOAD CONFIG FOREIGN KEY INSPECTION")
    print("=" * 100)

    if not rows:
        print("Constraint fk_load_mapping_version was not found.")
        return

    for row in rows:
        (
            constraint_name,
            source_schema,
            source_table,
            source_column,
            target_schema,
            target_table,
            target_column,
            constraint_definition,
        ) = row

        print(f"Constraint          : {constraint_name}")
        print(f"Source              : {source_schema}.{source_table}")
        print(f"Source Column       : {source_column}")
        print(f"Referenced Table    : {target_schema}.{target_table}")
        print(f"Referenced Column   : {target_column}")
        print(f"Definition          : {constraint_definition}")

    print()
    print("=" * 100)
    print("INSPECTION COMPLETED")
    print("Operation           : READ ONLY")
    print("Metadata modified   : NO")
    print("=" * 100)


def inspect_legacy_mapping_version(connection) -> None:
    """
    Check whether the legacy ingest.mapping_version table contains
    mapping version 2.

    Why:
        The error strongly suggests that load_config is referencing
        the legacy ingest.mapping_version table.
    """

    query = """
        SELECT
            mapping_version_id
        FROM ingest.mapping_version
        WHERE mapping_version_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (2,))
        row = cursor.fetchone()

    print()
    print("=" * 100)
    print("LEGACY INGEST MAPPING VERSION CHECK")
    print("=" * 100)

    if row is None:
        print("ingest.mapping_version ID 2 : NOT FOUND")
    else:
        print("ingest.mapping_version ID 2 : FOUND")

    print("map.mapping_version ID 2    : EXPECTED TO EXIST")
    print("=" * 100)


def main() -> None:
    """
    Execute both read-only inspections using the existing metastore
    connection manager.
    """

    with get_metastore_connection() as connection:
        inspect_load_config_fk(connection)
        inspect_legacy_mapping_version(connection)


# Standard Python module entry point.
if __name__ == "__main__":
    main()