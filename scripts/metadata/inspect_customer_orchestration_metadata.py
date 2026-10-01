"""
Customer Orchestration Metadata Inspection

Purpose
-------
Inspect the orchestration metadata required to create the Customer
full-load pipeline.

Tables inspected
----------------
    orch.pipeline
    orch.pipeline_version
    orch.pipeline_task
    orch.task_dependency
    orch.retry_policy
    orch.parameter

Why
---
Before inserting orchestration metadata, we need to verify the actual
database structure, constraints, defaults, and existing records.

This is especially important because earlier investigation showed that
legacy and new metadata schemas are not always structurally identical.

This script is READ ONLY.

It does NOT perform:
    INSERT
    UPDATE
    DELETE
    ALTER
    DROP
"""

from app.db.metastore import get_metastore_connection


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    Why:
    Consistent output makes the metadata inspection easier to review.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def print_table_structure(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Display the actual column structure of a table.

    Why:
    We should use the database's real schema instead of assuming
    column names from the application design.
    """

    print_section(
        f"TABLE STRUCTURE: {schema_name}.{table_name}"
    )

    query = """
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
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name, table_name),
        )

        print(
            "position | column_name | data_type | "
            "nullable | default"
        )

        rows = cursor.fetchall()

        if not rows:
            print("(TABLE NOT FOUND OR NO COLUMNS)")
            return

        for row in rows:
            print(row)


def print_constraints(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Display primary keys, foreign keys, unique constraints,
    and check constraints.

    Why:
    Orchestration inserts must respect the database's actual
    integrity rules.
    """

    print_section(
        f"CONSTRAINTS: {schema_name}.{table_name}"
    )

    query = """
        SELECT
            tc.constraint_name,
            tc.constraint_type
        FROM information_schema.table_constraints tc
        WHERE tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY
            tc.constraint_type,
            tc.constraint_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name, table_name),
        )

        print(
            "constraint_name | constraint_type"
        )

        rows = cursor.fetchall()

        if not rows:
            print("(NO CONSTRAINTS FOUND)")
            return

        for row in rows:
            print(row)


def print_foreign_keys(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Display detailed foreign-key relationships.

    Why:
    Pipeline tasks can reference mapping versions, pipeline versions,
    retry policies, tenants, and principals. We need the actual
    relationships before creating records.
    """

    print_section(
        f"FOREIGN KEYS: {schema_name}.{table_name}"
    )

    query = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_schema AS referenced_schema,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
            AND tc.table_name = kcu.table_name
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s
          AND tc.table_name = %s
        ORDER BY tc.constraint_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name, table_name),
        )

        print(
            "constraint | column | referenced_schema | "
            "referenced_table | referenced_column"
        )

        rows = cursor.fetchall()

        if not rows:
            print("(NO FOREIGN KEYS FOUND)")
            return

        for row in rows:
            print(row)


def print_check_constraints(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Display CHECK constraint definitions.

    Why:
    CHECK constraints often define valid pipeline/task/status values.
    We need these values before creating Customer orchestration records.
    """

    print_section(
        f"CHECK CONSTRAINTS: {schema_name}.{table_name}"
    )

    query = """
        SELECT
            con.conname AS constraint_name,
            pg_get_constraintdef(con.oid) AS definition
        FROM pg_constraint con
        JOIN pg_class tbl
            ON tbl.oid = con.conrelid
        JOIN pg_namespace ns
            ON ns.oid = tbl.relnamespace
        WHERE ns.nspname = %s
          AND tbl.relname = %s
          AND con.contype = 'c'
        ORDER BY con.conname;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_name, table_name),
        )

        print(
            "constraint_name | definition"
        )

        rows = cursor.fetchall()

        if not rows:
            print("(NO CHECK CONSTRAINTS FOUND)")
            return

        for row in rows:
            print(row)


def print_existing_rows(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Display existing rows from an orchestration table.

    Why:
    Existing Employee orchestration metadata may show us the intended
    values and patterns for the Customer pipeline.

    The query is limited to a reasonable number of rows because this
    is an inspection script, not a bulk extraction utility.
    """

    print_section(
        f"EXISTING DATA: {schema_name}.{table_name}"
    )

    query = f"""
        SELECT *
        FROM {schema_name}.{table_name}
        ORDER BY 1
        LIMIT 20;
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


def inspect_table(
    connection,
    schema_name: str,
    table_name: str,
) -> None:
    """
    Run all read-only inspections for one orchestration table.
    """

    print_table_structure(
        connection,
        schema_name,
        table_name,
    )

    print_constraints(
        connection,
        schema_name,
        table_name,
    )

    print_foreign_keys(
        connection,
        schema_name,
        table_name,
    )

    print_check_constraints(
        connection,
        schema_name,
        table_name,
    )

    print_existing_rows(
        connection,
        schema_name,
        table_name,
    )


def main() -> None:
    """
    Inspect the orchestration metadata model.

    All database operations are SELECT statements only.
    """

    print("=" * 100)
    print("CUSTOMER ORCHESTRATION METADATA INSPECTION")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # --------------------------------------------------------------
        # Pipeline represents the stable identity of the orchestration.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "pipeline",
        )

        # --------------------------------------------------------------
        # Pipeline version represents an immutable/configurable version
        # of the pipeline.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "pipeline_version",
        )

        # --------------------------------------------------------------
        # Pipeline task connects the orchestration task to Mapping Version.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "pipeline_task",
        )

        # --------------------------------------------------------------
        # A single Customer task does not require a dependency, but we
        # inspect the table before deciding whether a dependency row
        # is necessary.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "task_dependency",
        )

        # --------------------------------------------------------------
        # Retry policy may be referenced by pipeline_task.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "retry_policy",
        )

        # --------------------------------------------------------------
        # Parameters are optional for the current Customer POC, but we
        # inspect the structure so we know whether any runtime parameter
        # is required.
        # --------------------------------------------------------------
        inspect_table(
            connection,
            "orch",
            "parameter",
        )

    print()
    print("=" * 100)
    print("CUSTOMER ORCHESTRATION METADATA INSPECTION COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    """
    Execute the inspection when this module is run directly.
    """

    main()