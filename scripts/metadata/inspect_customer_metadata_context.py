"""
Customer Metadata Context Inspection
====================================

Purpose
-------
Identify the tenant, project, environment, system, and existing metadata
context required before creating the Customer dataset metadata.

This script is READ-ONLY.

It does NOT:
    - INSERT records
    - UPDATE records
    - DELETE records
    - CREATE database objects
    - ALTER database objects
    - create target tables
    - execute ingestion

Why this inspection is required
-------------------------------
Connection 1 belongs to a specific tenant/system/environment.

catalog.dataset requires:
    tenant_id
    project_id

Therefore, we must identify a valid project for the connection's tenant
instead of guessing a project ID.

The intended metadata path is:

    Connection 1
        |
        +--> tenant_id
        +--> system_id
        +--> environment_id
        |
        v
    Valid project context
        |
        v
    catalog.dataset
        |
        v
    catalog.dataset_binding
"""


from __future__ import annotations

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC connection identifiers
# ---------------------------------------------------------------------------
# These are the already-created dynamic connections.
#
# Connection 1:
#   Source PostgreSQL database
#
# Connection 11:
#   Target PostgreSQL database
#
# We inspect them rather than creating new connections.
SOURCE_CONNECTION_ID = 1
TARGET_CONNECTION_ID = 11


def print_section(title: str) -> None:
    """
    Print a standard section heading.

    Keeping output formatting in one helper makes the inspection easier to
    read when executed from PowerShell.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def execute_and_print(
    connection: Any,
    title: str,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> list[tuple[Any, ...]]:
    """
    Execute a read-only query and print the result.

    Parameters are passed separately from SQL text so psycopg can safely
    bind them as PostgreSQL parameters.
    """

    print_section(title)

    with connection.cursor() as cursor:
        cursor.execute(query, parameters)

        rows = cursor.fetchall()

        column_names = [
            description.name
            for description in cursor.description
        ]

    if not rows:
        print("No rows returned.")
        return []

    print(" | ".join(column_names))
    print("-" * 100)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    print()
    print(f"Rows returned: {len(rows)}")

    return rows


def inspect_matching_tables(
    connection: Any,
    pattern: str,
) -> list[tuple[Any, ...]]:
    """
    Find metadata tables whose names match the supplied pattern.

    Why:
    The database contains several governance/control schemas and we should
    verify the actual tenant/project/environment table names instead of
    assuming them.
    """

    return execute_and_print(
        connection=connection,
        title=f"METADATA TABLES MATCHING: {pattern}",
        query="""
            SELECT
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE
                table_type = 'BASE TABLE'
                AND table_schema NOT IN (
                    'pg_catalog',
                    'information_schema'
                )
                AND LOWER(table_name) LIKE %s
            ORDER BY
                table_schema,
                table_name;
        """,
        parameters=(pattern,),
    )


def main() -> None:
    """
    Inspect the metadata context required for Customer registration.
    """

    print()
    print("=" * 100)
    print("CUSTOMER METADATA CONTEXT INSPECTION")
    print("=" * 100)

    print(f"Source Connection ID : {SOURCE_CONNECTION_ID}")
    print(f"Target Connection ID : {TARGET_CONNECTION_ID}")

    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # 1. Inspect both dynamic connection profiles
        # -------------------------------------------------------------------
        # This confirms the tenant/system/environment context attached to
        # each dynamic connection.
        execute_and_print(
            connection=connection,
            title="SOURCE CONNECTION CONTEXT",
            query="""
                SELECT
                    "connection_id",
                    "tenant_id",
                    "system_id",
                    "environment_id",
                    "connector_version_id",
                    "connection_role_code",
                    "connection_name",
                    "database_name",
                    "status_code"
                FROM conn.connection_profile
                WHERE "connection_id" = %s;
            """,
            parameters=(SOURCE_CONNECTION_ID,),
        )

        execute_and_print(
            connection=connection,
            title="TARGET CONNECTION CONTEXT",
            query="""
                SELECT
                    "connection_id",
                    "tenant_id",
                    "system_id",
                    "environment_id",
                    "connector_version_id",
                    "connection_role_code",
                    "connection_name",
                    "database_name",
                    "status_code"
                FROM conn.connection_profile
                WHERE "connection_id" = %s;
            """,
            parameters=(TARGET_CONNECTION_ID,),
        )

        # -------------------------------------------------------------------
        # 2. Discover actual tenant-related tables
        # -------------------------------------------------------------------
        # We do not assume where tenant metadata is stored.
        inspect_matching_tables(
            connection=connection,
            pattern="%tenant%",
        )

        # -------------------------------------------------------------------
        # 3. Discover actual project-related tables
        # -------------------------------------------------------------------
        # catalog.dataset requires project_id, so we need to identify the
        # authoritative project catalogue before creating a dataset.
        inspect_matching_tables(
            connection=connection,
            pattern="%project%",
        )

        # -------------------------------------------------------------------
        # 4. Discover actual environment-related tables
        # -------------------------------------------------------------------
        # Connection profiles reference environment_id. We need the actual
        # environment catalogue and its valid relationship to the tenant.
        inspect_matching_tables(
            connection=connection,
            pattern="%environment%",
        )

        # -------------------------------------------------------------------
        # 5. Discover actual system/source-system tables
        # -------------------------------------------------------------------
        # This helps establish how the current connection's system_id is
        # represented in the control-plane metadata.
        inspect_matching_tables(
            connection=connection,
            pattern="%system%",
        )

        # -------------------------------------------------------------------
        # 6. Inspect existing datasets grouped by tenant/project
        # -------------------------------------------------------------------
        # Existing records provide an example of how tenant and project
        # context is currently being used.
        execute_and_print(
            connection=connection,
            title="EXISTING CATALOG DATASETS BY TENANT/PROJECT",
            query="""
                SELECT
                    "tenant_id",
                    "project_id",
                    COUNT(*) AS dataset_count,
                    MIN("dataset_id") AS first_dataset_id,
                    MAX("dataset_id") AS last_dataset_id
                FROM catalog.dataset
                GROUP BY
                    "tenant_id",
                    "project_id"
                ORDER BY
                    "tenant_id",
                    "project_id";
            """,
        )

        # -------------------------------------------------------------------
        # 7. Inspect existing bindings grouped by tenant/connection
        # -------------------------------------------------------------------
        # This shows how catalog bindings currently associate tenants and
        # dynamic connection IDs.
        execute_and_print(
            connection=connection,
            title="EXISTING CATALOG BINDINGS BY TENANT/CONNECTION",
            query="""
                SELECT
                    "tenant_id",
                    "connection_id",
                    "environment_id",
                    COUNT(*) AS binding_count
                FROM catalog.dataset_binding
                GROUP BY
                    "tenant_id",
                    "connection_id",
                    "environment_id"
                ORDER BY
                    "tenant_id",
                    "connection_id",
                    "environment_id";
            """,
        )

        # -------------------------------------------------------------------
        # 8. Inspect catalog-related sequences
        # -------------------------------------------------------------------
        # Before creating metadata, it is useful to know whether identifiers
        # are generated by sequences or whether the application must obtain
        # IDs through another mechanism.
        execute_and_print(
            connection=connection,
            title="CATALOG SEQUENCE OBJECTS",
            query="""
                SELECT
                    sequence_schema,
                    sequence_name
                FROM information_schema.sequences
                WHERE
                    sequence_schema = 'catalog'
                ORDER BY sequence_name;
            """,
        )

        # -------------------------------------------------------------------
        # 9. Final status
        # -------------------------------------------------------------------
        print_section("INSPECTION COMPLETE")

        print("No metadata was modified.")
        print()
        print(
            "Use the results above to identify the valid tenant/project/"
            "environment context for Customer metadata."
        )
        print()
        print(
            "Do not insert catalog.dataset or catalog.dataset_binding "
            "records until the correct project context is confirmed."
        )


if __name__ == "__main__":
    # Run the inspection only when this module is executed directly.
    main()