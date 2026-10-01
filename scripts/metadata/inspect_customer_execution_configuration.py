"""
Customer Execution Configuration Inspection
============================================

Purpose:
    Inspect the exact metadata structures that configure execution for
    Mapping Version 2.

Tables inspected:

    ingest.load_config
    ingest.target_load_config
    orch.pipeline
    orch.pipeline_version
    orch.pipeline_task
    orch.task_dependency
    orch.parameter

Why this script exists:
    The platform already contains separate metadata models for:

        Load configuration
        Target write configuration
        Pipeline definition
        Pipeline version
        Pipeline task
        Task dependency
        Runtime execution

    We must use the existing model rather than inventing another
    execution-plan table.

Important:
    This script is completely READ-ONLY.

    It does not:
        INSERT
        UPDATE
        DELETE
        CREATE
        ALTER
        DROP
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Customer mapping context
# ---------------------------------------------------------------------------
# These values were already created and validated successfully.
TENANT_ID = 1
PROJECT_ID = 1
MAPPING_ID = 2
MAPPING_VERSION_ID = 2


# ---------------------------------------------------------------------------
# Tables that participate in execution configuration/orchestration.
# ---------------------------------------------------------------------------
TABLES_TO_INSPECT = (
    ("ingest", "load_config"),
    ("ingest", "target_load_config"),
    ("orch", "pipeline"),
    ("orch", "pipeline_version"),
    ("orch", "pipeline_task"),
    ("orch", "task_dependency"),
    ("orch", "parameter"),
)


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    This makes the output easier to read during development.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def inspect_table_definition(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect the complete column definition of one table.

    We use information_schema because it reflects the live PostgreSQL
    database rather than relying on assumptions from an older design file.
    """

    print_section(
        f"TABLE DEFINITION: {schema_name}.{table_name}"
    )

    with connection.cursor() as cursor:

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

    if not columns:
        raise LookupError(
            f"Table {schema_name}.{table_name} was not found."
        )

    print(
        "Ordinal | Column | Data Type | Nullable | Default"
    )
    print("-" * 100)

    for (
        ordinal_position,
        column_name,
        data_type,
        is_nullable,
        column_default,
    ) in columns:

        print(
            f"{ordinal_position:>7} | "
            f"{column_name:<40} | "
            f"{data_type:<25} | "
            f"{is_nullable:<8} | "
            f"{column_default}"
        )


def inspect_constraints(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect primary-key, unique, check, and foreign-key constraints.

    Why:
        Knowing the columns alone is not enough.

        For example, target_load_config may have one row per mapping
        version because mapping_version_id could be its primary key.

        We need the live constraint definition before inserting metadata.
    """

    print_section(
        f"CONSTRAINTS: {schema_name}.{table_name}"
    )

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                tc.constraint_name,
                tc.constraint_type,
                kcu.column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
               AND tc.constraint_schema = kcu.constraint_schema
               AND tc.table_schema = kcu.table_schema
               AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY
                tc.constraint_name,
                kcu.ordinal_position;
            """,
            (
                schema_name,
                table_name,
            ),
        )

        constraints = cursor.fetchall()

    if not constraints:
        print("No constraints discovered.")
        return

    for (
        constraint_name,
        constraint_type,
        column_name,
    ) in constraints:

        print(
            f"{constraint_type:<20} "
            f"{constraint_name:<60} "
            f"{column_name}"
        )


def inspect_existing_rows(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect existing rows for the table.

    Existing metadata is useful because it shows how the platform
    currently populates these structures.

    Only a small sample is returned.
    """

    print_section(
        f"EXISTING METADATA: {schema_name}.{table_name}"
    )

    with connection.cursor() as cursor:

        # Table and column names come from controlled metadata discovered
        # from information_schema, not from external user input.
        query = (
            f'SELECT * '
            f'FROM "{schema_name}"."{table_name}" '
            f'LIMIT 10;'
        )

        cursor.execute(query)

        rows = cursor.fetchall()

        if not rows:
            print("No rows found.")
            return

        column_names = [
            description.name
            for description in cursor.description
        ]

    print("Columns:")
    print(" | ".join(column_names))

    print()
    print("Rows:")

    for row in rows:
        print(row)


def inspect_customer_rows(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Inspect only metadata related to Customer Mapping Version 2.

    This is especially important for tables such as load_config,
    target_load_config, pipeline_task, and parameter.
    """

    print_section(
        f"CUSTOMER-SPECIFIC METADATA: "
        f"{schema_name}.{table_name}"
    )

    with connection.cursor() as cursor:

        # mapping_version_id is the common execution configuration
        # reference for the Customer mapping.
        #
        # Not every table has mapping_version_id, so the query is
        # selected based on the known table structures.
        if table_name in (
            "load_config",
            "target_load_config",
        ):

            cursor.execute(
                f"""
                SELECT *
                FROM "{schema_name}"."{table_name}"
                WHERE mapping_version_id = %s;
                """,
                (MAPPING_VERSION_ID,),
            )

        elif table_name == "pipeline_task":

            cursor.execute(
                """
                SELECT *
                FROM orch.pipeline_task
                WHERE mapping_version_id = %s;
                """,
                (MAPPING_VERSION_ID,),
            )

        elif table_name == "parameter":

            cursor.execute(
                """
                SELECT *
                FROM orch.parameter
                WHERE mapping_version_id = %s
                   OR pipeline_version_id IN
                      (
                          SELECT pipeline_version_id
                          FROM orch.pipeline_task
                          WHERE mapping_version_id = %s
                      );
                """,
                (
                    MAPPING_VERSION_ID,
                    MAPPING_VERSION_ID,
                ),
            )

        else:
            print(
                "Customer-specific mapping filter is not applicable "
                "to this table."
            )
            return

        rows = cursor.fetchall()

        if not rows:
            print(
                "No Customer-specific metadata currently exists."
            )
            return

        column_names = [
            description.name
            for description in cursor.description
        ]

    print("Columns:")
    print(" | ".join(column_names))

    print()
    print("Rows:")

    for row in rows:
        print(row)


def main() -> None:
    """
    Execute the complete read-only execution configuration inspection.
    """

    print_section(
        "CUSTOMER EXECUTION CONFIGURATION INSPECTION"
    )

    with get_metastore_connection() as connection:

        # ---------------------------------------------------------------
        # Inspect table structures.
        # ---------------------------------------------------------------
        for schema_name, table_name in TABLES_TO_INSPECT:

            inspect_table_definition(
                connection,
                schema_name,
                table_name,
            )

            inspect_constraints(
                connection,
                schema_name,
                table_name,
            )

            inspect_existing_rows(
                connection,
                schema_name,
                table_name,
            )

            inspect_customer_rows(
                connection,
                schema_name,
                table_name,
            )

    print_section(
        "CUSTOMER EXECUTION CONFIGURATION INSPECTION COMPLETED"
    )

    print(f"Tenant ID         : {TENANT_ID}")
    print(f"Project ID        : {PROJECT_ID}")
    print(f"Mapping ID        : {MAPPING_ID}")
    print(f"Mapping Version   : {MAPPING_VERSION_ID}")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")


if __name__ == "__main__":
    main()