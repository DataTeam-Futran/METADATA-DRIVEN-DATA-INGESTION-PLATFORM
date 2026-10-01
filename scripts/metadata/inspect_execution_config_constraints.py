"""
Execution Configuration Constraint Inspection
=============================================

Purpose:
    Inspect the actual CHECK constraint definitions used by the ingestion
    and orchestration metadata tables.

Why this is required:
    The previous metadata inspection showed only constraint names.
    Before inserting production metadata, we need to know the exact
    allowed values for configuration fields.

This script is READ-ONLY.
It does not insert, update, or delete any metadata.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Tables whose CHECK constraints are important for the Customer full-load
# execution configuration.
#
# We inspect both ingestion configuration and orchestration configuration
# because these tables will control how the Customer pipeline executes.
# ---------------------------------------------------------------------------
TABLES_TO_INSPECT = [
    "ingest.load_config",
    "ingest.target_load_config",
    "orch.pipeline",
    "orch.pipeline_version",
    "orch.pipeline_task",
    "orch.task_dependency",
    "orch.parameter",
]


def inspect_constraints(connection, table_name: str) -> None:
    """
    Print the CHECK constraint definitions for one metadata table.

    Why:
        PostgreSQL stores the actual constraint expression in pg_constraint.
        pg_get_constraintdef() converts that internal definition into readable
        SQL, allowing us to see permitted configuration values.
    """

    query = """
        SELECT
            conname,
            pg_get_constraintdef(oid) AS constraint_definition
        FROM pg_constraint
        WHERE conrelid = %s::regclass
          AND contype = 'c'
        ORDER BY conname;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        rows = cursor.fetchall()

    print()
    print("=" * 100)
    print(f"CHECK CONSTRAINTS: {table_name}")
    print("=" * 100)

    # If no CHECK constraints exist, explicitly report that instead of
    # producing an empty section.
    if not rows:
        print("No CHECK constraints found.")
        return

    # Print each constraint exactly as PostgreSQL defines it.
    for constraint_name, constraint_definition in rows:
        print(f"Constraint : {constraint_name}")
        print(f"Definition : {constraint_definition}")
        print("-" * 100)


def main() -> None:
    """
    Main execution function.

    The metastore connection is read-only from this script's perspective.
    No commit is required because we do not modify any database state.
    """

    print("=" * 100)
    print("EXECUTION CONFIGURATION CONSTRAINT INSPECTION")
    print("=" * 100)

    # Use the existing centralized metadata-store connection manager.
    with get_metastore_connection() as connection:

        # Inspect every relevant metadata table.
        for table_name in TABLES_TO_INSPECT:
            inspect_constraints(connection, table_name)

    print()
    print("=" * 100)
    print("EXECUTION CONFIGURATION CONSTRAINT INSPECTION COMPLETED")
    print("Operation       : READ ONLY")
    print("Metadata modified: NO")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Standard Python entry point.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()