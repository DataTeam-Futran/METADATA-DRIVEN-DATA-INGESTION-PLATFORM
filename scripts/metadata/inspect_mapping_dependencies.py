"""
Inspect Mapping Dependencies
============================

Purpose:
    Inspect the production-style metadata dependencies for a specific
    map.mapping_version.

Why this script exists:
    Before creating or modifying Customer metadata, we need to understand
    exactly how the existing mapping metadata is connected.

    This script inspects:

        map.mapping
              |
              v
        map.mapping_version
              |
        +-----+-------------------+
        |                         |
        v                         v
    map.mapping_source       map.mapping_field
                                  |
                                  v
                          map.mapping_field_input

    It also resolves the parent mapping_id and the source/target references
    stored in mapping_version.

Important:
    This script is READ-ONLY.
    It does NOT insert, update, delete, or modify metadata.

Current POC:
    Mapping Version ID = 1

    The script is intentionally schema-driven because the metadata database
    contains production-style tables whose exact column names must be
    discovered from PostgreSQL rather than assumed.
"""

from __future__ import annotations

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# This is the mapping version that we want to inspect.
#
# Why:
# Mapping Version 1 is the currently existing published/active mapping
# that we are studying before creating the Customer full-load metadata.
MAPPING_VERSION_ID = 1


# ---------------------------------------------------------------------------
# Utility: print section heading
# ---------------------------------------------------------------------------
def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    Why:
        Makes the terminal output easier to read when several metadata
        tables are inspected in sequence.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ---------------------------------------------------------------------------
# Utility: inspect table structure
# ---------------------------------------------------------------------------
def inspect_table_structure(
    connection: Any,
    schema_name: str,
    table_name: str,
) -> list[str]:
    """
    Retrieve the actual column names from information_schema.

    Why:
        We do not want to hardcode assumptions about production metadata
        column names. This also helps detect schema differences early.
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

    columns = [row[0] for row in rows]

    print(f"\n{schema_name}.{table_name}")
    print("-" * 100)

    if not columns:
        print("Table not found or contains no visible columns.")
        return []

    for index, column_name in enumerate(columns, start=1):
        print(f"{index:>3}. {column_name}")

    return columns


# ---------------------------------------------------------------------------
# Utility: inspect table data
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

    Parameters:
        connection:
            Active PostgreSQL connection.

        schema_name:
            Metadata schema, for example 'map'.

        table_name:
            Metadata table, for example 'mapping_version'.

        columns:
            Columns to display.

        where_clause:
            Optional SQL WHERE clause.

        parameters:
            Parameters corresponding to placeholders in where_clause.

    Why:
        Centralizing this logic prevents repeated SQL and makes the script
        easier to maintain.

    Important psycopg rule:
        For one parameter use:

            parameters=(value,)

        NOT:

            parameters=((value,),)

        The latter creates a nested tuple and PostgreSQL may interpret the
        tuple itself as the parameter value.
    """

    if not columns:
        return []

    # Quote identifiers because metadata column names are database objects.
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
        # IMPORTANT:
        # If there are no parameters, pass an empty tuple.
        # If parameters exist, pass them directly.
        cursor.execute(
            query,
            parameters if parameters is not None else (),
        )

        rows = cursor.fetchall()

    if not rows:
        print("No rows found.")
        return []

    # Print column headers.
    print(" | ".join(columns))
    print("-" * 100)

    # Print data.
    for row in rows:
        print(
            " | ".join(
                "NULL" if value is None else str(value)
                for value in row
            )
        )

    print(f"\nRows returned: {len(rows)}")

    return rows


# ---------------------------------------------------------------------------
# Main inspection logic
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Inspect the complete dependency chain for Mapping Version 1.
    """

    print_section("MAPPING DEPENDENCY INSPECTION")

    print(
        f"Mapping Version ID: {MAPPING_VERSION_ID}"
    )

    # -----------------------------------------------------------------------
    # Open metadata database connection.
    # -----------------------------------------------------------------------
    #
    # Why:
    # All mapping metadata is stored in the metadata/control database.
    #
    # The connection helper is responsible only for opening and closing
    # the database connection. This script performs READ-ONLY operations.
    with get_metastore_connection() as connection:

        # ================================================================
        # 1. Inspect map.mapping
        # ================================================================
        mapping_columns = inspect_table_structure(
            connection=connection,
            schema_name="map",
            table_name="mapping",
        )

        # ================================================================
        # 2. Inspect map.mapping_version structure
        # ================================================================
        mapping_version_columns = inspect_table_structure(
            connection=connection,
            schema_name="map",
            table_name="mapping_version",
        )

        # ================================================================
        # 3. Read Mapping Version
        # ================================================================
        #
        # IMPORTANT:
        # Use (MAPPING_VERSION_ID,) instead of
        # ((MAPPING_VERSION_ID,),).
        #
        # Why:
        # psycopg expects one positional parameter as a one-element tuple.
        mapping_version_rows = inspect_table_data(
            connection=connection,
            schema_name="map",
            table_name="mapping_version",
            columns=mapping_version_columns,
            where_clause='"mapping_version_id" = %s',
            parameters=(MAPPING_VERSION_ID,),
        )

        if not mapping_version_rows:
            print(
                "\nERROR: Mapping Version ID "
                f"{MAPPING_VERSION_ID} was not found."
            )
            return

        # ================================================================
        # 4. Resolve parent mapping_id
        # ================================================================
        #
        # Why:
        # map.mapping_version contains mapping_id, which connects the
        # version to the parent map.mapping record.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    "mapping_id"
                FROM map.mapping_version
                WHERE "mapping_version_id" = %s;
                """,
                (MAPPING_VERSION_ID,),
            )

            row = cursor.fetchone()

        if row is None:
            print(
                "\nERROR: Unable to resolve mapping_id."
            )
            return

        mapping_id = row[0]

        print()
        print(
            f"Resolved mapping_id: {mapping_id}"
        )

        # ================================================================
        # 5. Inspect parent map.mapping
        # ================================================================
        #
        # Why:
        # This confirms the business-level mapping definition associated
        # with the selected mapping version.
        inspect_table_data(
            connection=connection,
            schema_name="map",
            table_name="mapping",
            columns=mapping_columns,
            where_clause='"mapping_id" = %s',
            parameters=(mapping_id,),
        )

        # ================================================================
        # 6. Inspect map.mapping_source
        # ================================================================
        #
        # Why:
        # mapping_source identifies the source dataset/schema version
        # participating in the mapping and provides the source alias.
        mapping_source_columns = inspect_table_structure(
            connection=connection,
            schema_name="map",
            table_name="mapping_source",
        )

        inspect_table_data(
            connection=connection,
            schema_name="map",
            table_name="mapping_source",
            columns=mapping_source_columns,
            where_clause='"mapping_version_id" = %s',
            parameters=(MAPPING_VERSION_ID,),
        )

        # ================================================================
        # 7. Inspect map.mapping_field
        # ================================================================
        #
        # Why:
        # mapping_field defines how each target field is populated.
        #
        # It contains information such as:
        #   - target_field_id
        #   - mapping_type_code
        #   - datatype_mapping_rule_id
        #   - transform_expression
        #   - null_rule_code
        #   - key_role_code
        #   - ordinal_no
        mapping_field_columns = inspect_table_structure(
            connection=connection,
            schema_name="map",
            table_name="mapping_field",
        )

        mapping_field_rows = inspect_table_data(
            connection=connection,
            schema_name="map",
            table_name="mapping_field",
            columns=mapping_field_columns,
            where_clause='"mapping_version_id" = %s',
            parameters=(MAPPING_VERSION_ID,),
        )

        # ================================================================
        # 8. Resolve mapping_field_ids
        # ================================================================
        #
        # Why:
        # mapping_field_input references mapping_field_id.
        # We therefore first collect the mapping field IDs and then inspect
        # the corresponding input records.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    "mapping_field_id"
                FROM map.mapping_field
                WHERE "mapping_version_id" = %s
                ORDER BY "mapping_field_id";
                """,
                (MAPPING_VERSION_ID,),
            )

            mapping_field_ids = [
                row[0]
                for row in cursor.fetchall()
            ]

        print()
        print(
            "Resolved mapping_field_ids:"
        )

        if mapping_field_ids:
            print(
                ", ".join(
                    str(value)
                    for value in mapping_field_ids
                )
            )
        else:
            print("None")

        # ================================================================
        # 9. Inspect map.mapping_field_input
        # ================================================================
        #
        # Why:
        # mapping_field_input connects each target mapping field to its
        # source field.
        #
        # Example relationship:
        #
        # source_field_id
        #        |
        #        v
        # mapping_field_input
        #        |
        #        v
        # mapping_field
        #        |
        #        v
        # target_field_id
        mapping_field_input_columns = inspect_table_structure(
            connection=connection,
            schema_name="map",
            table_name="mapping_field_input",
        )

        if mapping_field_ids:
            inspect_table_data(
                connection=connection,
                schema_name="map",
                table_name="mapping_field_input",
                columns=mapping_field_input_columns,
                where_clause='"mapping_field_id" = ANY(%s)',
                parameters=(mapping_field_ids,),
            )
        else:
            print_section(
                "DATA: map.mapping_field_input"
            )
            print(
                "Skipped because no mapping_field_id values were found."
            )

        # ================================================================
        # 10. Summary
        # ================================================================
        print_section("MAPPING DEPENDENCY SUMMARY")

        print(
            f"Mapping Version ID : {MAPPING_VERSION_ID}"
        )

        print(
            f"Parent Mapping ID  : {mapping_id}"
        )

        print(
            f"Mapping Fields     : {len(mapping_field_rows)}"
        )

        print(
            f"Mapping Field IDs  : "
            f"{mapping_field_ids if mapping_field_ids else 'None'}"
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