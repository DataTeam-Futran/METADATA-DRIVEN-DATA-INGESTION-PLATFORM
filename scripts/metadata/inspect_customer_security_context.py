"""
Customer Security and Execution Context Inspection
====================================================

Purpose:
    Inspect the tenant, project, environment, and source-system metadata
    required before creating production-style Customer catalog metadata.

Why this script is required:
    The conn.connection_profile records already tell us that Source
    Connection 1 and Target Connection 11 belong to tenant 1 and
    environment 1.

    However, catalog.dataset requires a valid project_id.

    We must therefore identify the project that belongs to tenant 1
    instead of guessing or reusing a project from another tenant.

Important:
    This script is READ-ONLY.

    It does not insert, update, delete, or modify any metadata.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Helper function
# ---------------------------------------------------------------------------
# This function executes a query and prints the returned rows in a simple
# tabular format. It keeps the inspection logic reusable and readable.
def print_query_results(
    connection,
    title: str,
    query: str,
    parameters: tuple = (),
) -> None:
    """Execute a read-only query and print the results."""

    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)

    with connection.cursor() as cursor:
        # Execute only SELECT statements because this script is intended
        # strictly for metadata inspection.
        cursor.execute(query, parameters)

        # Read column names so the output is self-describing.
        columns = [description.name for description in cursor.description]

        # Fetch all rows returned by the inspection query.
        rows = cursor.fetchall()

    if not rows:
        print("No rows returned.")
        return

    # Print column headers.
    print(" | ".join(columns))
    print("-" * 100)

    # Print every returned metadata record.
    for row in rows:
        print(" | ".join(str(value) for value in row))

    print(f"\nRows returned: {len(rows)}")


# ---------------------------------------------------------------------------
# Main inspection function
# ---------------------------------------------------------------------------
def main() -> None:
    """Inspect the metadata context required for Customer registration."""

    print("=" * 100)
    print("CUSTOMER SECURITY / PROJECT CONTEXT INSPECTION")
    print("=" * 100)

    # These are the already validated dynamic connections from our POC.
    source_connection_id = 1
    target_connection_id = 11

    # Open one metadata-store connection for all read-only inspection queries.
    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # 1. Inspect Tenant 1
        # -------------------------------------------------------------------
        # Connection 1 and Connection 11 both belong to tenant 1.
        # We now inspect the tenant record to identify its business identity.
        print_query_results(
            connection,
            "TENANT 1",
            """
            SELECT
                *
            FROM sec.tenant
            WHERE tenant_id = %s
            ORDER BY tenant_id;
            """,
            (1,),
        )

        # -------------------------------------------------------------------
        # 2. Inspect Projects belonging to Tenant 1
        # -------------------------------------------------------------------
        # This is the most important query in this step.
        #
        # catalog.dataset requires project_id, so we need to find the
        # project that belongs to the same tenant as our dynamic connections.
        print_query_results(
            connection,
            "PROJECTS BELONGING TO TENANT 1",
            """
            SELECT
                *
            FROM sec.project
            WHERE tenant_id = %s
            ORDER BY project_id;
            """,
            (1,),
        )

        # -------------------------------------------------------------------
        # 3. Inspect Environment 1
        # -------------------------------------------------------------------
        # The connection metadata already tells us environment_id = 1.
        # This query confirms the actual environment record and its status.
        print_query_results(
            connection,
            "ENVIRONMENT 1",
            """
            SELECT
                *
            FROM sec.environment
            WHERE environment_id = %s
            ORDER BY environment_id;
            """,
            (1,),
        )

        # -------------------------------------------------------------------
        # 4. Inspect Source System 1
        # -------------------------------------------------------------------
        # Connection 1 and Connection 11 both belong to system_id = 1.
        # We inspect the system record so the complete execution context
        # is documented before creating catalog metadata.
        print_query_results(
            connection,
            "SOURCE SYSTEM 1",
            """
            SELECT
                *
            FROM conn.source_system
            WHERE system_id = %s
            ORDER BY system_id;
            """,
            (1,),
        )

        # -------------------------------------------------------------------
        # 5. Reconfirm source and target context together
        # -------------------------------------------------------------------
        # This final query makes sure that both connections belong to the
        # same tenant/system/environment context.
        print_query_results(
            connection,
            "SOURCE + TARGET CONTEXT RECONFIRMATION",
            """
            SELECT
                connection_id,
                tenant_id,
                system_id,
                environment_id,
                connection_role_code,
                connection_name,
                database_name,
                status_code
            FROM conn.connection_profile
            WHERE connection_id IN (%s, %s)
            ORDER BY connection_id;
            """,
            (source_connection_id, target_connection_id),
        )

    # -----------------------------------------------------------------------
    # Completion message
    # -----------------------------------------------------------------------
    # No INSERT/UPDATE/DELETE statements exist in this script, so no
    # transaction commit is required.
    print("\n" + "=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# ---------------------------------------------------------------------------
# Python module entry point
# ---------------------------------------------------------------------------
# This allows the script to be executed using:
#
#     python -m scripts.metadata.inspect_customer_security_context
#
if __name__ == "__main__":
    main()