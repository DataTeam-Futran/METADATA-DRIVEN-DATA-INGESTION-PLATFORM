"""
Inspect Catalog Schema Version Metadata
=======================================

Purpose
-------
Inspect the actual structure and foreign-key relationships of:

    catalog.dataset_schema_version

Why this is needed
------------------
The target schema version will need to reference the target dataset
and its physical binding.

Before inserting target schema metadata, we must verify exactly what
the existing metadata model allows.

In particular, we need to understand:

    source_binding_id

and determine whether the existing model expects:

    - only source bindings
    - both source and target bindings
    - a generic dataset binding despite the column name

This script is READ-ONLY.

No metadata is inserted, updated, or deleted.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Inspect table columns
# ---------------------------------------------------------------------------


def inspect_columns(connection) -> None:
    """
    Display the actual columns defined on catalog.dataset_schema_version.
    """

    query = """
        SELECT
            ordinal_position,
            column_name,
            data_type,
            is_nullable,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'catalog'
          AND table_name = 'dataset_schema_version'
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("DATASET_SCHEMA_VERSION COLUMNS")
    print("-" * 72)

    for row in rows:
        (
            ordinal_position,
            column_name,
            data_type,
            is_nullable,
            column_default,
        ) = row

        print(
            f"{ordinal_position}. "
            f"{column_name} | "
            f"{data_type} | "
            f"Nullable={is_nullable} | "
            f"Default={column_default}"
        )


# ---------------------------------------------------------------------------
# Inspect foreign keys
# ---------------------------------------------------------------------------


def inspect_foreign_keys(connection) -> None:
    """
    Display all foreign-key relationships defined for
    catalog.dataset_schema_version.

    This tells us exactly what the metadata model allows the schema
    version to reference.
    """

    query = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_schema AS referenced_schema,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints AS tc
        INNER JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            AND tc.table_name = kcu.table_name
        INNER JOIN information_schema.constraint_column_usage AS ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'catalog'
          AND tc.table_name = 'dataset_schema_version'
        ORDER BY
            tc.constraint_name,
            kcu.ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("FOREIGN KEYS")
    print("-" * 72)

    if not rows:
        print("No foreign keys found.")
        return

    for row in rows:
        (
            constraint_name,
            column_name,
            referenced_schema,
            referenced_table,
            referenced_column,
        ) = row

        print(
            f"{constraint_name} : "
            f"{column_name} -> "
            f"{referenced_schema}.{referenced_table}."
            f"{referenced_column}"
        )


# ---------------------------------------------------------------------------
# Inspect existing schema-version records
# ---------------------------------------------------------------------------


def inspect_existing_records(connection) -> None:
    """
    Display existing schema-version records.

    This helps us understand how source_binding_id is currently used
    in the metadata already present in the database.
    """

    query = """
        SELECT
            schema_version_id,
            tenant_id,
            dataset_id,
            source_binding_id,
            schema_capture_run_id,
            version_no,
            source_code,
            change_type_code,
            is_current
        FROM catalog.dataset_schema_version
        ORDER BY schema_version_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    print()
    print("EXISTING SCHEMA VERSION RECORDS")
    print("-" * 72)

    if not rows:
        print("No schema-version records found.")
        return

    for row in rows:
        (
            schema_version_id,
            tenant_id,
            dataset_id,
            source_binding_id,
            schema_capture_run_id,
            version_no,
            source_code,
            change_type_code,
            is_current,
        ) = row

        print(
            f"Schema Version ID={schema_version_id} | "
            f"Tenant={tenant_id} | "
            f"Dataset={dataset_id} | "
            f"Binding={source_binding_id} | "
            f"Capture Run={schema_capture_run_id} | "
            f"Version={version_no} | "
            f"Source Code={source_code} | "
            f"Change={change_type_code} | "
            f"Current={is_current}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Execute all read-only metadata inspections.
    """

    print("=" * 72)
    print("SCHEMA VERSION METADATA INSPECTION")
    print("=" * 72)

    with get_metastore_connection() as connection:

        # Inspect the physical metadata table definition.
        inspect_columns(connection)

        # Inspect FK relationships.
        inspect_foreign_keys(connection)

        # Inspect how existing records use the columns.
        inspect_existing_records(connection)

    print()
    print("=" * 72)
    print("INSPECTION COMPLETED")
    print("=" * 72)

    print()
    print("No metadata changes were made.")


if __name__ == "__main__":
    main()