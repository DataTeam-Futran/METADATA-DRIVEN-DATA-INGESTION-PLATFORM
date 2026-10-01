"""
Orchestration Preflight Inspection

Purpose
-------
Perform the final READ-ONLY validation before creating the Customer
pipeline, pipeline version, and pipeline task.

The Customer orchestration will use:

    Tenant ID          = 1
    Project ID         = 1
    Mapping Version ID = 2

Before inserting records, this script verifies:

    1. Tenant 1 exists.
    2. Project 1 exists.
    3. Mapping Version 2 exists.
    4. Mapping Version 2 belongs to Tenant 1.
    5. Pipeline task mapping_version_id FK points to map.mapping_version.
    6. Pipeline/task primary-key generation behavior.
    7. Existing Customer pipeline does not already exist.

This script is READ ONLY.

No INSERT, UPDATE, DELETE, ALTER, or DROP operations are performed.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Customer orchestration identifiers.
#
# These are metadata identifiers already established during the previous
# development steps. They are validated below before being used.
# ---------------------------------------------------------------------------
TENANT_ID = 1
PROJECT_ID = 1
MAPPING_VERSION_ID = 2

PIPELINE_CODE = "CUSTOMER_FULL_LOAD_PIPELINE"


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    Why:
    Consistent output makes the preflight results easy to review.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def check_tenant(connection) -> None:
    """
    Verify that Tenant 1 exists.

    Why:
    orch.pipeline.tenant_id is a required foreign key.
    """

    query = """
        SELECT
            tenant_id
        FROM sec.tenant
        WHERE tenant_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (TENANT_ID,))
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Tenant ID {TENANT_ID} was not found in sec.tenant."
        )

    print(
        f"Tenant verification: PASSED "
        f"(tenant_id={TENANT_ID})"
    )


def check_project(connection) -> None:
    """
    Verify that Project 1 exists and belongs to Tenant 1.

    Why:
    orch.pipeline contains both tenant_id and project_id, and the
    project relationship must be valid before pipeline creation.
    """

    query = """
        SELECT
            project_id,
            tenant_id
        FROM sec.project
        WHERE project_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (PROJECT_ID,))
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Project ID {PROJECT_ID} was not found in sec.project."
        )

    project_id, project_tenant_id = row

    if project_tenant_id != TENANT_ID:
        raise RuntimeError(
            f"Project {PROJECT_ID} belongs to tenant "
            f"{project_tenant_id}, not tenant {TENANT_ID}."
        )

    print(
        f"Project verification: PASSED "
        f"(project_id={project_id}, tenant_id={project_tenant_id})"
    )


def check_mapping_version(connection) -> None:
    """
    Verify Customer Mapping Version 2.

    Why:
    orch.pipeline_task.mapping_version_id must point to the
    authoritative new map.mapping_version record.
    """

    query = """
        SELECT
            mapping_version_id,
            tenant_id,
            mapping_id,
            version_no,
            load_type_code,
            load_strategy_code,
            status_code
        FROM map.mapping_version
        WHERE mapping_version_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (MAPPING_VERSION_ID,),
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Mapping Version {MAPPING_VERSION_ID} "
            "was not found in map.mapping_version."
        )

    (
        mapping_version_id,
        tenant_id,
        mapping_id,
        version_no,
        load_type,
        load_strategy,
        status,
    ) = row

    if tenant_id != TENANT_ID:
        raise RuntimeError(
            f"Mapping Version {MAPPING_VERSION_ID} belongs to "
            f"tenant {tenant_id}, not tenant {TENANT_ID}."
        )

    print("Mapping Version verification: PASSED")
    print(f"  Mapping Version ID : {mapping_version_id}")
    print(f"  Tenant ID          : {tenant_id}")
    print(f"  Mapping ID         : {mapping_id}")
    print(f"  Version Number     : {version_no}")
    print(f"  Load Type          : {load_type}")
    print(f"  Load Strategy      : {load_strategy}")
    print(f"  Status             : {status}")


def inspect_pipeline_task_foreign_keys(connection) -> None:
    """
    Inspect pipeline_task foreign keys directly through pg_constraint.

    Why:
    The earlier information_schema output listed the mapping-version
    constraint but did not display it in the detailed FK section.

    pg_constraint is PostgreSQL's authoritative constraint catalog.
    """

    print_section(
        "PIPELINE TASK FOREIGN KEY DEFINITIONS"
    )

    query = """
        SELECT
            con.conname AS constraint_name,
            source_schema.nspname AS source_schema,
            source_table.relname AS source_table,
            source_column.attname AS source_column,
            target_schema.nspname AS target_schema,
            target_table.relname AS target_table,
            target_column.attname AS target_column,
            pg_get_constraintdef(con.oid) AS constraint_definition
        FROM pg_constraint con
        JOIN pg_class source_table
            ON source_table.oid = con.conrelid
        JOIN pg_namespace source_schema
            ON source_schema.oid = source_table.relnamespace
        JOIN pg_class target_table
            ON target_table.oid = con.confrelid
        JOIN pg_namespace target_schema
            ON target_schema.oid = target_table.relnamespace
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
          AND source_schema.nspname = 'orch'
          AND source_table.relname = 'pipeline_task'
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
            raise RuntimeError(
                "No foreign keys were found on orch.pipeline_task."
            )

        for row in rows:
            print(row)


def inspect_identity_columns(connection) -> None:
    """
    Inspect identity/sequence information for orchestration IDs.

    Why:
    The information_schema output showed no column_default for the
    primary-key columns. We need to determine how PostgreSQL generates
    pipeline_id, pipeline_version_id, and task_id.
    """

    print_section(
        "ORCHESTRATION PRIMARY KEY GENERATION"
    )

    query = """
        SELECT
            table_schema,
            table_name,
            column_name,
            is_identity,
            identity_generation,
            column_default
        FROM information_schema.columns
        WHERE table_schema = 'orch'
          AND table_name IN (
              'pipeline',
              'pipeline_version',
              'pipeline_task'
          )
          AND column_name IN (
              'pipeline_id',
              'pipeline_version_id',
              'task_id'
          )
        ORDER BY
            table_name,
            ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)

        print(
            "table | column | is_identity | "
            "identity_generation | column_default"
        )

        rows = cursor.fetchall()

        for row in rows:
            print(row)


def check_existing_customer_pipeline(connection) -> None:
    """
    Check whether the Customer pipeline already exists.

    Why:
    orch.pipeline has a unique constraint on:
        tenant_id + project_id + pipeline_code

    We should not accidentally create a duplicate pipeline.
    """

    print_section(
        "CUSTOMER PIPELINE DUPLICATE CHECK"
    )

    query = """
        SELECT
            pipeline_id,
            tenant_id,
            project_id,
            pipeline_code,
            pipeline_name,
            status_code,
            pipeline_type_code
        FROM orch.pipeline
        WHERE tenant_id = %s
          AND project_id = %s
          AND pipeline_code = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TENANT_ID,
                PROJECT_ID,
                PIPELINE_CODE,
            ),
        )

        rows = cursor.fetchall()

    if rows:
        print(
            "WARNING: Customer pipeline already exists."
        )

        for row in rows:
            print(row)
    else:
        print(
            "Customer pipeline duplicate check: PASSED"
        )
        print(
            "No existing pipeline found for the requested "
            "tenant/project/pipeline code."
        )


def main() -> None:
    """
    Execute the complete orchestration preflight.

    All operations are read-only.
    """

    print("=" * 100)
    print("CUSTOMER ORCHESTRATION PREFLIGHT")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # --------------------------------------------------------------
        # Validate the tenant that will own the pipeline.
        # --------------------------------------------------------------
        check_tenant(connection)

        # --------------------------------------------------------------
        # Validate the project that will own the pipeline.
        # --------------------------------------------------------------
        check_project(connection)

        # --------------------------------------------------------------
        # Validate Customer Mapping Version 2.
        # --------------------------------------------------------------
        check_mapping_version(connection)

        # --------------------------------------------------------------
        # Verify pipeline-task FK relationships.
        # --------------------------------------------------------------
        inspect_pipeline_task_foreign_keys(connection)

        # --------------------------------------------------------------
        # Determine whether orchestration primary keys are generated
        # automatically by PostgreSQL.
        # --------------------------------------------------------------
        inspect_identity_columns(connection)

        # --------------------------------------------------------------
        # Prevent accidental duplicate pipeline creation.
        # --------------------------------------------------------------
        check_existing_customer_pipeline(connection)

    print()
    print("=" * 100)
    print("CUSTOMER ORCHESTRATION PREFLIGHT COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    """
    Execute the preflight when this module is run directly.
    """

    main()