"""
Inspect Catalog and Datatype Dependencies
=========================================

Purpose:
    Inspect the production-style catalog and datatype metadata that
    are referenced by the existing mapping_version.

Why:
    The existing map.mapping_version contains references such as:

        primary_source_dataset_id
        primary_source_schema_version_id
        target_dataset_id
        target_schema_version_id
        datatype_mapping_set_id

    Before creating Customer metadata, we must understand what these
    IDs actually reference.

Important:
    This script is READ-ONLY.

    It does NOT:
        - insert metadata
        - update metadata
        - delete metadata
        - modify the existing Employee mapping

Current reference:
    Mapping Version ID = 1
"""


from __future__ import annotations

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Existing Employee mapping version that we are using only as a reference.
#
# Why:
# Mapping Version 1 already contains valid production-style metadata.
# Studying its dependencies tells us how the metadata model is intended
# to work before we create the Customer configuration.
MAPPING_VERSION_ID = 1


# ---------------------------------------------------------------------------
# Utility: print section heading
# ---------------------------------------------------------------------------
def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    Why:
        Makes the terminal output easier to read when inspecting multiple
        metadata tables.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ---------------------------------------------------------------------------
# Inspect all tables in a schema
# ---------------------------------------------------------------------------
def inspect_schema_tables(
    connection: Any,
    schema_name: str,
) -> list[str]:
    """
    Return all base tables in a metadata schema.

    Why:
        We do not assume the names of catalog or datatype tables.
        The PostgreSQL metadata database is the source of truth.
    """

    query = """
        SELECT
            table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name,),
        )

        rows = cursor.fetchall()

    tables = [row[0] for row in rows]

    print_section(
        f"TABLES IN SCHEMA: {schema_name}"
    )

    if not tables:
        print("No tables found.")
        return []

    for table_name in tables:
        print(table_name)

    print()
    print(f"Table count: {len(tables)}")

    return tables


# ---------------------------------------------------------------------------
# Inspect table columns
# ---------------------------------------------------------------------------
def inspect_table_columns(
    connection: Any,
    schema_name: str,
    table_name: str,
) -> list[str]:
    """
    Retrieve the actual columns for a table.

    Why:
        This prevents us from making assumptions about production metadata
        column names.
    """

    query = """
        SELECT
            column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name, table_name),
        )

        rows = cursor.fetchall()

    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Inspect table rows
# ---------------------------------------------------------------------------
def inspect_table_data(
    connection: Any,
    schema_name: str,
    table_name: str,
    columns: list[str],
    where_clause: str | None = None,
    parameters: tuple[Any, ...] | None = None,
) -> list[tuple[Any, ...]]:
    """
    Read rows from a metadata table.

    Important psycopg parameter rule:

        Correct:
            parameters=(1,)

        Incorrect:
            parameters=((1,),)

    The second form creates a nested tuple and can result in PostgreSQL
    trying to convert "(1)" into a bigint.
    """

    if not columns:
        print(
            f"No columns found for {schema_name}.{table_name}."
        )
        return []

    quoted_columns = ", ".join(
        f'"{column}"'
        for column in columns
    )

    query = f"""
        SELECT
            {quoted_columns}
        FROM "{schema_name}"."{table_name}"
    """

    if where_clause:
        query += f"\nWHERE {where_clause}"

    query += ";"

    print_section(
        f"DATA: {schema_name}.{table_name}"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            parameters if parameters is not None else (),
        )

        rows = cursor.fetchall()

    if not rows:
        print("No rows found.")
        return []

    print(" | ".join(columns))
    print("-" * 100)

    for row in rows:
        print(
            " | ".join(
                "NULL" if value is None else str(value)
                for value in row
            )
        )

    print()
    print(f"Rows returned: {len(rows)}")

    return rows


# ---------------------------------------------------------------------------
# Inspect foreign keys for selected schemas
# ---------------------------------------------------------------------------
def inspect_foreign_keys(
    connection: Any,
    schema_names: tuple[str, ...],
) -> None:
    """
    Display foreign-key relationships for the supplied schemas.

    Why:
        This tells us exactly how catalog, datatype, mapping and ingestion
        metadata are connected.

    We use information_schema instead of assuming FK relationships.
    """

    query = """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.table_schema AS referenced_schema,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column,
            tc.constraint_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON tc.constraint_name = ccu.constraint_name
           AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = ANY(%s)
        ORDER BY
            tc.table_schema,
            tc.table_name,
            tc.constraint_name,
            kcu.ordinal_position;
    """

    print_section(
        "FOREIGN KEY DEPENDENCIES"
    )

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (list(schema_names),),
        )

        rows = cursor.fetchall()

    if not rows:
        print("No foreign-key relationships found.")
        return

    print(
        "TABLE | COLUMN | REFERENCES | REFERENCED COLUMN | CONSTRAINT"
    )
    print("-" * 100)

    for row in rows:
        (
            table_schema,
            table_name,
            column_name,
            referenced_schema,
            referenced_table,
            referenced_column,
            constraint_name,
        ) = row

        print(
            f"{table_schema}.{table_name} | "
            f"{column_name} | "
            f"{referenced_schema}.{referenced_table} | "
            f"{referenced_column} | "
            f"{constraint_name}"
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Inspect catalog and datatype dependencies for Mapping Version 1.
    """

    print_section(
        "CATALOG AND DATATYPE DEPENDENCY INSPECTION"
    )

    print(
        f"Reference Mapping Version ID: {MAPPING_VERSION_ID}"
    )

    with get_metastore_connection() as connection:

        # ================================================================
        # 1. Discover catalog tables
        # ================================================================
        #
        # Why:
        # Customer metadata will eventually need to be registered in the
        # correct catalog structures.
        catalog_tables = inspect_schema_tables(
            connection=connection,
            schema_name="catalog",
        )

        # ================================================================
        # 2. Discover datatype tables
        # ================================================================
        #
        # Why:
        # Customer fields need datatype metadata and the mapping version
        # currently references datatype_mapping_set_id = 1.
        dtype_tables = inspect_schema_tables(
            connection=connection,
            schema_name="dtype",
        )

        # ================================================================
        # 3. Discover foreign-key relationships
        # ================================================================
        #
        # Why:
        # This is the most important part of this step. We want to know
        # exactly what tables the IDs in map.mapping_version reference.
        inspect_foreign_keys(
            connection=connection,
            schema_names=(
                "catalog",
                "dtype",
                "map",
                "ingest",
            ),
        )

        # ================================================================
        # 4. Read the existing mapping_version references
        # ================================================================
        #
        # We intentionally read the actual values from the database rather
        # than hardcoding them.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    "mapping_version_id",
                    "primary_source_dataset_id",
                    "primary_source_schema_version_id",
                    "target_dataset_id",
                    "target_schema_version_id",
                    "datatype_mapping_set_id",
                    "load_type_code",
                    "load_strategy_code",
                    "status_code"
                FROM map.mapping_version
                WHERE "mapping_version_id" = %s;
                """,
                (MAPPING_VERSION_ID,),
            )

            mapping_row = cursor.fetchone()

        if mapping_row is None:
            print(
                f"\nMapping Version {MAPPING_VERSION_ID} not found."
            )
            return

        (
            mapping_version_id,
            source_dataset_id,
            source_schema_version_id,
            target_dataset_id,
            target_schema_version_id,
            datatype_mapping_set_id,
            load_type_code,
            load_strategy_code,
            status_code,
        ) = mapping_row

        # ================================================================
        # 5. Print resolved references
        # ================================================================
        print_section(
            "RESOLVED MAPPING REFERENCES"
        )

        print(
            f"Mapping Version ID          : {mapping_version_id}"
        )

        print(
            f"Primary Source Dataset ID   : {source_dataset_id}"
        )

        print(
            f"Primary Source Schema ID    : {source_schema_version_id}"
        )

        print(
            f"Target Dataset ID           : {target_dataset_id}"
        )

        print(
            f"Target Schema Version ID    : {target_schema_version_id}"
        )

        print(
            f"Datatype Mapping Set ID     : {datatype_mapping_set_id}"
        )

        print(
            f"Load Type                   : {load_type_code}"
        )

        print(
            f"Load Strategy               : {load_strategy_code}"
        )

        print(
            f"Status                      : {status_code}"
        )

        # ================================================================
        # 6. Inspect discovered table structures
        # ================================================================
        #
        # We do not yet know which catalog table owns dataset_id or
        # schema_version_id. Therefore we print the structures first.
        print_section(
            "CATALOG TABLE STRUCTURES"
        )

        for table_name in catalog_tables:
            columns = inspect_table_columns(
                connection=connection,
                schema_name="catalog",
                table_name=table_name,
            )

            print(
                f"\n catalog.{table_name}"
            )

            for index, column in enumerate(
                columns,
                start=1,
            ):
                print(
                    f"   {index:>3}. {column}"
                )

        print_section(
            "DATATYPE TABLE STRUCTURES"
        )

        for table_name in dtype_tables:
            columns = inspect_table_columns(
                connection=connection,
                schema_name="dtype",
                table_name=table_name,
            )

            print(
                f"\n dtype.{table_name}"
            )

            for index, column in enumerate(
                columns,
                start=1,
            ):
                print(
                    f"   {index:>3}. {column}"
                )

        # ================================================================
        # 7. Summary
        # ================================================================
        print_section(
            "INSPECTION SUMMARY"
        )

        print(
            f"Catalog tables discovered : {len(catalog_tables)}"
        )

        print(
            f"Datatype tables discovered: {len(dtype_tables)}"
        )

        print(
            f"Source Dataset ID         : {source_dataset_id}"
        )

        print(
            f"Source Schema Version ID  : {source_schema_version_id}"
        )

        print(
            f"Target Dataset ID         : {target_dataset_id}"
        )

        print(
            f"Target Schema Version ID  : {target_schema_version_id}"
        )

        print(
            f"Datatype Mapping Set ID   : {datatype_mapping_set_id}"
        )

        print()
        print(
            "Inspection completed successfully."
        )

        print(
            "No metadata was inserted, updated, or deleted."
        )


# ---------------------------------------------------------------------------
# Python entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()