"""
Inspect Catalog and Datatype Metadata Model
===========================================

This is a READ-ONLY investigation script.

It does not:
    - INSERT
    - UPDATE
    - DELETE
    - CREATE
    - ALTER
    - TRUNCATE
    - COMMIT metadata changes

The purpose is to inspect the actual metadata model before we create the
Customer dataset metadata for the full-load POC.

Execution path being investigated:

    Connection 1
        |
        v
    catalog.dataset
        |
        v
    catalog.dataset_binding
        |
        v
    catalog.schema_capture_run
        |
        v
    catalog.dataset_schema_version
        |
        v
    catalog.dataset_field
        |
        v
    dtype.datatype_mapping_rule
"""

from __future__ import annotations

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Known POC identifiers
# ---------------------------------------------------------------------------
# These identifiers are already established in the current development
# environment. They are used only for filtering inspection results.
SOURCE_CONNECTION_ID = 1
TARGET_CONNECTION_ID = 11

# PostgreSQL native datatype IDs already discovered during previous inspection.
POSTGRES_INTEGER_TYPE_ID = 62
POSTGRES_VARCHAR_TYPE_ID = 73

# Datatype mapping set already discovered.
DATATYPE_MAPPING_SET_ID = 1


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    A common formatter makes the PowerShell output easier to read while
    comparing several metadata tables.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def print_rows(
    rows: list[tuple[Any, ...]],
    column_names: list[str],
) -> None:
    """
    Print query results in a simple pipe-separated format.

    This keeps the script dependency-free and makes the output easy to paste
    back into the development conversation.
    """

    if not rows:
        print("No rows returned.")
        return

    print(" | ".join(column_names))
    print("-" * 100)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    print()
    print(f"Rows returned: {len(rows)}")


def execute_and_print(
    connection: Any,
    title: str,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> list[tuple[Any, ...]]:
    """
    Execute a read-only query and print its result.

    Parameters are always passed separately from SQL text. This is important
    for psycopg because values containing '%' must not be interpolated into
    SQL strings.
    """

    print_section(title)

    with connection.cursor() as cursor:
        cursor.execute(query, parameters)

        rows = cursor.fetchall()

        column_names = [
            description.name
            for description in cursor.description
        ]

    print_rows(rows, column_names)

    return rows


def inspect_table_definition(
    connection: Any,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect the real PostgreSQL column definition of a table.

    information_schema.columns is used instead of assuming column names.
    This avoids the problem encountered earlier where a guessed column such
    as status_code did not exist in dtype.datatype_mapping_rule.
    """

    execute_and_print(
        connection=connection,
        title=f"TABLE DEFINITION: {schema_name}.{table_name}",
        query="""
            SELECT
                ordinal_position,
                column_name,
                data_type,
                udt_schema,
                udt_name,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE
                table_schema = %s
                AND table_name = %s
            ORDER BY ordinal_position;
        """,
        parameters=(schema_name, table_name),
    )


def inspect_foreign_keys(
    connection: Any,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect foreign-key relationships for a table.

    The PostgreSQL catalog is used because it provides the exact constraint
    relationships, including the referenced schema/table/column.

    This is important before inserting metadata because we need to know the
    correct parent records that must exist first.
    """

    execute_and_print(
        connection=connection,
        title=f"FOREIGN KEYS: {schema_name}.{table_name}",
        query="""
            SELECT
                tc.constraint_name,
                kcu.column_name AS child_column,
                ccu.table_schema AS parent_schema,
                ccu.table_name AS parent_table,
                ccu.column_name AS parent_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON tc.constraint_name = ccu.constraint_name
                AND tc.table_schema = ccu.table_schema
            WHERE
                tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = %s
                AND tc.table_name = %s
            ORDER BY
                tc.constraint_name,
                kcu.ordinal_position;
        """,
        parameters=(schema_name, table_name),
    )


def inspect_existing_rows(
    connection: Any,
    schema_name: str,
    table_name: str,
    limit: int = 10,
) -> None:
    """
    Display a small sample of existing records.

    Existing records are useful because they show how this database's
    metadata has actually been populated, including tenant IDs, status codes,
    audit fields, and relationships.
    """

    # The schema/table names in this script are fixed internal metadata
    # identifiers rather than user-provided SQL. They are therefore safe to
    # compose into this inspection query.
    query = f"""
        SELECT *
        FROM "{schema_name}"."{table_name}"
        LIMIT %s;
    """

    execute_and_print(
        connection=connection,
        title=f"EXISTING ROW SAMPLE: {schema_name}.{table_name}",
        query=query,
        parameters=(limit,),
    )


def inspect_datatype_rules_for_type(
    connection: Any,
    native_datatype_id: int,
    type_label: str,
) -> None:
    """
    Find datatype rules involving one native datatype ID.

    We intentionally select all columns using SELECT * because the actual
    datatype-rule structure has not yet been fully verified.

    This lets PostgreSQL tell us the real rule model rather than making
    assumptions about columns such as status_code, quality codes, or
    conversion columns.
    """

    execute_and_print(
        connection=connection,
        title=(
            f"DATATYPE RULES INVOLVING {type_label} "
            f"(NATIVE DATATYPE ID {native_datatype_id})"
        ),
        query="""
            SELECT *
            FROM dtype.datatype_mapping_rule
            WHERE
                "mapping_set_id" = %s
                AND (
                    "source_native_datatype_id" = %s
                    OR "target_native_datatype_id" = %s
                )
            ORDER BY
                "mapping_rule_id"
            LIMIT 100;
        """,
        parameters=(
            DATATYPE_MAPPING_SET_ID,
            native_datatype_id,
            native_datatype_id,
        ),
    )


def main() -> None:
    """
    Run the complete read-only metadata model investigation.
    """

    print()
    print("=" * 100)
    print("CATALOG + DATATYPE METADATA MODEL INSPECTION")
    print("=" * 100)

    print(f"Source Connection ID    : {SOURCE_CONNECTION_ID}")
    print(f"Target Connection ID    : {TARGET_CONNECTION_ID}")
    print(f"Datatype Mapping Set ID : {DATATYPE_MAPPING_SET_ID}")
    print(f"PostgreSQL INTEGER ID   : {POSTGRES_INTEGER_TYPE_ID}")
    print(f"PostgreSQL VARCHAR ID    : {POSTGRES_VARCHAR_TYPE_ID}")

    # Open the central metadata-store database using the application's
    # standard connection manager. No source or target password is printed.
    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # 1. Inspect catalog table definitions
        # -------------------------------------------------------------------
        # These definitions are the foundation for the metadata capture flow.
        catalog_tables = [
            ("catalog", "dataset"),
            ("catalog", "dataset_binding"),
            ("catalog", "schema_capture_run"),
            ("catalog", "dataset_schema_version"),
            ("catalog", "dataset_field"),
        ]

        for schema_name, table_name in catalog_tables:
            inspect_table_definition(
                connection=connection,
                schema_name=schema_name,
                table_name=table_name,
            )

        # -------------------------------------------------------------------
        # 2. Inspect datatype rule definition
        # -------------------------------------------------------------------
        # This is especially important because the previous query proved that
        # guessed columns should not be used against dtype.datatype_mapping_rule.
        inspect_table_definition(
            connection=connection,
            schema_name="dtype",
            table_name="datatype_mapping_rule",
        )

        # -------------------------------------------------------------------
        # 3. Inspect datatype mapping-set definition
        # -------------------------------------------------------------------
        # The mapping set is the parent/versioned release that owns rules.
        inspect_table_definition(
            connection=connection,
            schema_name="dtype",
            table_name="datatype_mapping_set",
        )

        # -------------------------------------------------------------------
        # 4. Inspect foreign-key relationships for catalog tables
        # -------------------------------------------------------------------
        # The order in which metadata can be created depends on these
        # relationships. For example, a dataset field cannot reference a
        # schema version that does not exist.
        for schema_name, table_name in catalog_tables:
            inspect_foreign_keys(
                connection=connection,
                schema_name=schema_name,
                table_name=table_name,
            )

        # -------------------------------------------------------------------
        # 5. Inspect datatype-rule foreign keys
        # -------------------------------------------------------------------
        # This tells us which catalogue records the datatype rules reference.
        inspect_foreign_keys(
            connection=connection,
            schema_name="dtype",
            table_name="datatype_mapping_rule",
        )

        # -------------------------------------------------------------------
        # 6. Inspect existing catalog examples
        # -------------------------------------------------------------------
        # We inspect a small sample rather than dumping the complete catalog.
        # This gives us established examples to follow for Customer metadata.
        for schema_name, table_name in catalog_tables:
            inspect_existing_rows(
                connection=connection,
                schema_name=schema_name,
                table_name=table_name,
                limit=10,
            )

        # -------------------------------------------------------------------
        # 7. Inspect existing datatype rules
        # -------------------------------------------------------------------
        # We search both source and target references for INTEGER and
        # CHARACTER VARYING. This is broader than the earlier exact 62 -> 62
        # query and can reveal the actual crosswalk model.
        inspect_datatype_rules_for_type(
            connection=connection,
            native_datatype_id=POSTGRES_INTEGER_TYPE_ID,
            type_label="INTEGER",
        )

        inspect_datatype_rules_for_type(
            connection=connection,
            native_datatype_id=POSTGRES_VARCHAR_TYPE_ID,
            type_label="CHARACTER VARYING",
        )

        # -------------------------------------------------------------------
        # 8. Inspect all rules in the selected mapping set
        # -------------------------------------------------------------------
        # This final limited sample helps us understand how the mapping set
        # represents rules without making assumptions about the rule columns.
        execute_and_print(
            connection=connection,
            title="DATATYPE MAPPING RULE SAMPLE FOR SET 1",
            query="""
                SELECT *
                FROM dtype.datatype_mapping_rule
                WHERE "mapping_set_id" = %s
                ORDER BY "mapping_rule_id"
                LIMIT 25;
            """,
            parameters=(DATATYPE_MAPPING_SET_ID,),
        )

        # -------------------------------------------------------------------
        # 9. Final status
        # -------------------------------------------------------------------
        print_section("INSPECTION COMPLETE")

        print("No metadata was modified.")
        print()
        print("The next implementation decision will be based on:")
        print("1. Actual catalog table definitions.")
        print("2. Actual catalog foreign-key dependencies.")
        print("3. Existing catalog metadata examples.")
        print("4. Actual datatype mapping-rule structure.")
        print("5. Existing INTEGER and CHARACTER VARYING rules.")
        print()
        print(
            "Do not insert Customer metadata until these results are "
            "reviewed."
        )


if __name__ == "__main__":
    # Execute the inspection only when this module is run directly.
    main()
