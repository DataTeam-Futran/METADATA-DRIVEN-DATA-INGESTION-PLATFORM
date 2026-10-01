"""
Legacy Mapping Data Inspection

Purpose
-------
Inspect the actual structure and data of the legacy mapping tables.

Why this version is different
------------------------------
The previous inspection assumed that the legacy
ingest.mapping_field table contained columns such as:

    source_field_id
    target_field_id

PostgreSQL reported that source_field_id does not exist.

Therefore, instead of assuming the legacy schema matches the new
map.mapping_field schema, this script dynamically discovers the
actual columns from PostgreSQL.

This is important because:

    ingest.* = legacy metadata model
    map.*    = new metadata model

The two models may have different structures.

This script is READ ONLY.

It does NOT perform:
    INSERT
    UPDATE
    DELETE
    ALTER
    DROP
"""

from psycopg import sql

from app.db.metastore import get_metastore_connection


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    Why:
    Consistent output makes the metadata investigation easier
    to follow and document.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def get_table_columns(
    connection,
    schema_name: str,
    table_name: str,
) -> list[str]:
    """
    Retrieve the actual column names for a PostgreSQL table.

    Why:
    We do not want to assume that legacy tables have the same
    columns as the newer map.* tables.
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

        # Return the columns in their physical definition order.
        return [row[0] for row in cursor.fetchall()]


def print_table_structure(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Print the actual PostgreSQL structure of a table.

    Why:
    This lets us see exactly what columns exist before writing
    any queries against the table.
    """

    columns = get_table_columns(
        connection,
        schema_name,
        table_name,
    )

    print_section(
        f"TABLE STRUCTURE: {schema_name}.{table_name}"
    )

    if not columns:
        print("Table not found or no columns returned.")
        return

    print("Column count:", len(columns))

    for position, column_name in enumerate(
        columns,
        start=1,
    ):
        print(
            f"{position:02d}. {column_name}"
        )


def print_full_table(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Print every row from a table using its real column structure.

    Why:
    SELECT * avoids incorrectly assuming legacy column names.

    The table and schema names are controlled constants in this
    development script, so they are safely quoted using psycopg.sql.
    """

    print_section(
        f"DATA: {schema_name}.{table_name}"
    )

    # Safely quote the schema and table identifiers.
    query = sql.SQL(
        "SELECT * FROM {}.{}"
    ).format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )

    with connection.cursor() as cursor:
        cursor.execute(query)

        # Retrieve the actual column names returned by PostgreSQL.
        columns = [
            description.name
            for description in cursor.description
        ]

        print(" | ".join(columns))

        rows = cursor.fetchall()

        if not rows:
            print("(NO ROWS)")
            return

        for row in rows:
            print(row)


def print_mapping_version_usage(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Print mapping_version_id usage when the table contains that column.

    Why:
    This helps us understand which legacy mapping versions are
    actually referenced by each child table.

    The function checks the real table structure first instead of
    assuming that mapping_version_id exists.
    """

    columns = get_table_columns(
        connection,
        schema_name,
        table_name,
    )

    if "mapping_version_id" not in columns:
        print(
            f"{schema_name}.{table_name} "
            "does not contain mapping_version_id."
        )
        return

    print_section(
        f"MAPPING VERSION USAGE: {schema_name}.{table_name}"
    )

    query = sql.SQL(
        """
        SELECT
            mapping_version_id,
            COUNT(*) AS row_count
        FROM {}.{}
        GROUP BY mapping_version_id
        ORDER BY mapping_version_id;
        """
    ).format(
        sql.Identifier(schema_name),
        sql.Identifier(table_name),
    )

    with connection.cursor() as cursor:
        cursor.execute(query)

        print(
            "mapping_version_id | row_count"
        )

        rows = cursor.fetchall()

        if not rows:
            print("(NO ROWS)")
            return

        for row in rows:
            print(row)


def print_new_customer_mapping_fields(
    connection,
) -> None:
    """
    Inspect Customer mapping fields from the NEW map.* model.

    Why:
    The Customer mapping is already known to use mapping_version_id = 2.
    This gives us the new-model representation for comparison with
    the legacy metadata.
    """

    print_section(
        "NEW MODEL: map.mapping_field - CUSTOMER VERSION 2"
    )

    query = """
        SELECT
            mapping_field_id,
            tenant_id,
            mapping_version_id,
            target_field_id,
            mapping_type_code,
            transform_function_id,
            lookup_id,
            datatype_mapping_rule_id,
            transform_expression,
            expression_language_code,
            null_rule_code,
            default_value,
            format_mask,
            key_role_code,
            scd_behavior_code,
            ordinal_no
        FROM map.mapping_field
        WHERE mapping_version_id = 2
        ORDER BY ordinal_no, mapping_field_id;
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
            print("(NO ROWS)")
            return

        for row in rows:
            print(row)


def print_new_customer_mapping_sources(
    connection,
) -> None:
    """
    Inspect Customer mapping sources from the NEW map.* model.

    Why:
    This shows how Customer version 2 represents its source in the
    new metadata architecture.
    """

    print_section(
        "NEW MODEL: map.mapping_source - CUSTOMER VERSION 2"
    )

    query = """
        SELECT
            mapping_source_id,
            tenant_id,
            mapping_version_id,
            dataset_id,
            schema_version_id,
            source_alias,
            sequence_no,
            is_primary
        FROM map.mapping_source
        WHERE mapping_version_id = 2
        ORDER BY sequence_no, mapping_source_id;
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
            print("(NO ROWS)")
            return

        for row in rows:
            print(row)


def main() -> None:
    """
    Execute the complete legacy mapping investigation.

    Important:
    Every database operation in this function is read-only.
    """

    print("=" * 100)
    print("LEGACY MAPPING DATA INSPECTION")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # --------------------------------------------------------------
        # 1. Inspect the legacy mapping_version structure and data.
        #
        # Why:
        # This is the parent table for the legacy mapping metadata.
        # --------------------------------------------------------------
        print_table_structure(
            connection,
            "ingest",
            "mapping_version",
        )

        print_full_table(
            connection,
            "ingest",
            "mapping_version",
        )

        # --------------------------------------------------------------
        # 2. Inspect the legacy mapping_field structure and data.
        #
        # Why:
        # We previously assumed column names that do not exist.
        # SELECT * lets PostgreSQL show us the actual legacy structure.
        # --------------------------------------------------------------
        print_table_structure(
            connection,
            "ingest",
            "mapping_field",
        )

        print_mapping_version_usage(
            connection,
            "ingest",
            "mapping_field",
        )

        print_full_table(
            connection,
            "ingest",
            "mapping_field",
        )

        # --------------------------------------------------------------
        # 3. Inspect the legacy mapping_source structure and data.
        #
        # Why:
        # Mapping versions 1, 3 and 4 are currently referenced here.
        # We need to see exactly what these records represent.
        # --------------------------------------------------------------
        print_table_structure(
            connection,
            "ingest",
            "mapping_source",
        )

        print_mapping_version_usage(
            connection,
            "ingest",
            "mapping_source",
        )

        print_full_table(
            connection,
            "ingest",
            "mapping_source",
        )

        # --------------------------------------------------------------
        # 4. Inspect the legacy load_config structure and data.
        #
        # Why:
        # The existing load configuration references mapping version 1.
        # --------------------------------------------------------------
        print_table_structure(
            connection,
            "ingest",
            "load_config",
        )

        print_mapping_version_usage(
            connection,
            "ingest",
            "load_config",
        )

        print_full_table(
            connection,
            "ingest",
            "load_config",
        )

        # --------------------------------------------------------------
        # 5. Inspect the new Customer mapping fields.
        #
        # Why:
        # This provides the new-model representation that will eventually
        # drive Customer full-load execution.
        # --------------------------------------------------------------
        print_new_customer_mapping_fields(
            connection
        )

        # --------------------------------------------------------------
        # 6. Inspect the new Customer mapping sources.
        #
        # Why:
        # This confirms the source side of Customer mapping version 2.
        # --------------------------------------------------------------
        print_new_customer_mapping_sources(
            connection
        )

    print()
    print("=" * 100)
    print("LEGACY MAPPING DATA INSPECTION COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    """
    Run the inspection when this module is executed directly.
    """

    main()