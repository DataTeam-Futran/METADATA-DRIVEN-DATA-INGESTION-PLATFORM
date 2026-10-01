"""
Mapping Version Dependency Inspection
=====================================

Purpose:
    Determine which tables depend on ingest.mapping_version and compare
    the legacy mapping model with the new map.mapping_version model.

Why:
    ingest.load_config currently references ingest.mapping_version,
    while the new Customer mapping exists in map.mapping_version.

Before changing the foreign key, we must understand the impact on
existing metadata.

This script is READ-ONLY.
No INSERT, UPDATE, DELETE, ALTER, or DROP operations are performed.
"""

from app.db.metastore import get_metastore_connection


def inspect_legacy_mapping_versions(connection) -> None:
    """
    Display existing rows from the legacy ingest.mapping_version table.

    Why:
        We need to know whether the legacy mapping model contains active
        configuration that could be affected by a schema migration.
    """

    query = """
        SELECT *
        FROM ingest.mapping_version
        ORDER BY mapping_version_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)

        # Read the column names so the output remains useful even if the
        # legacy table contains more columns than currently expected.
        column_names = [description.name for description in cursor.description]

        rows = cursor.fetchall()

    print()
    print("=" * 100)
    print("LEGACY TABLE: ingest.mapping_version")
    print("=" * 100)

    if not rows:
        print("No rows found.")
        return

    print("Columns:")
    print(" | ".join(column_names))

    print()
    print("Rows:")

    for row in rows:
        print(row)


def inspect_load_config_rows(connection) -> None:
    """
    Display all existing ingest.load_config records.

    Why:
        These rows currently depend on ingest.mapping_version.
        We need to preserve their referential integrity during any
        future schema migration.
    """

    query = """
        SELECT
            load_config_id,
            mapping_version_id,
            load_type_code,
            batch_size,
            truncate_before_load,
            is_active
        FROM ingest.load_config
        ORDER BY load_config_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("=" * 100)
    print("EXISTING TABLE: ingest.load_config")
    print("=" * 100)

    if not rows:
        print("No rows found.")
        return

    print(
        "load_config_id | mapping_version_id | load_type_code | "
        "batch_size | truncate_before_load | is_active"
    )

    for row in rows:
        print(row)


def inspect_foreign_keys_referencing_legacy_mapping(connection) -> None:
    """
    Find every foreign key in the database that references
    ingest.mapping_version.

    Why:
        Changing one FK is safe only after we understand whether other
        metadata tables also depend on the legacy mapping table.
    """

    query = """
        SELECT
            source_ns.nspname AS source_schema,
            source_tbl.relname AS source_table,
            source_col.attname AS source_column,
            con.conname AS constraint_name,
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
        WHERE con.contype = 'f'
          AND target_ns.nspname = 'ingest'
          AND target_tbl.relname = 'mapping_version'
        ORDER BY
            source_ns.nspname,
            source_tbl.relname,
            source_col.attname;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("=" * 100)
    print("FOREIGN KEYS REFERENCING ingest.mapping_version")
    print("=" * 100)

    if not rows:
        print("No foreign keys found.")
        return

    for row in rows:
        (
            source_schema,
            source_table,
            source_column,
            constraint_name,
            target_schema,
            target_table,
            target_column,
            constraint_definition,
        ) = row

        print(f"Source              : {source_schema}.{source_table}")
        print(f"Source Column       : {source_column}")
        print(f"Constraint           : {constraint_name}")
        print(f"Target              : {target_schema}.{target_table}")
        print(f"Target Column       : {target_column}")
        print(f"Definition          : {constraint_definition}")
        print("-" * 100)


def inspect_new_mapping_versions(connection) -> None:
    """
    Display the new map.mapping_version rows relevant to the Customer flow.

    Why:
        This confirms the new metadata model is the intended source of
        mapping-version identity for the Customer pipeline.
    """

    query = """
        SELECT
            mapping_version_id,
            tenant_id,
            mapping_id,
            version_no,
            primary_source_dataset_id,
            primary_source_schema_version_id,
            target_dataset_id,
            target_schema_version_id,
            datatype_mapping_set_id,
            load_type_code,
            load_strategy_code,
            status_code
        FROM map.mapping_version
        ORDER BY mapping_version_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("=" * 100)
    print("NEW TABLE: map.mapping_version")
    print("=" * 100)

    if not rows:
        print("No rows found.")
        return

    print(
        "mapping_version_id | tenant_id | mapping_id | version_no | "
        "source_dataset | source_schema | target_dataset | target_schema | "
        "datatype_set | load_type | load_strategy | status"
    )

    for row in rows:
        print(row)


def main() -> None:
    """
    Execute the complete dependency inspection using one read-only
    metastore connection.
    """

    print("=" * 100)
    print("MAPPING VERSION DEPENDENCY IMPACT ANALYSIS")
    print("=" * 100)

    with get_metastore_connection() as connection:
        # Inspect the legacy mapping model.
        inspect_legacy_mapping_versions(connection)

        # Inspect existing load configuration.
        inspect_load_config_rows(connection)

        # Identify every FK depending on the legacy mapping table.
        inspect_foreign_keys_referencing_legacy_mapping(connection)

        # Inspect the newer mapping model.
        inspect_new_mapping_versions(connection)

    print()
    print("=" * 100)
    print("MAPPING VERSION DEPENDENCY ANALYSIS COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    main()