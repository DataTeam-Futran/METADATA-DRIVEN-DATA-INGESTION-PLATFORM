"""
Connector Version Capability Structure Inspection

Purpose
-------
Inspect the physical structure of:

    conn.connector_version_capability

We already confirmed that this table is the association between:

    connector_version
            |
            v
    connector_version_capability
            |
            v
    connector_capability

The current PostgreSQL connector version 3 has no capability assignments.

Before inserting the required POC capabilities, this script verifies:

1. Table columns.
2. Primary key.
3. Foreign keys.
4. Unique constraints.
5. Existing rows.

IMPORTANT
---------
This script is completely READ-ONLY.

No metadata is modified.
"""

# ============================================================================
# IMPORTS
# ============================================================================

# PostgreSQL driver used for the database connection type hint.
import psycopg

# Centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ============================================================================
# CONSTANTS
# ============================================================================

# The association table we are inspecting.
TABLE_SCHEMA = "conn"
TABLE_NAME = "connector_version_capability"


# ============================================================================
# OUTPUT HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    This makes the terminal output easier to review.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# TABLE COLUMNS
# ============================================================================

def inspect_columns(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect the physical columns of connector_version_capability.
    """

    print_section(
        "CONNECTOR VERSION CAPABILITY COLUMNS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # information_schema gives us the actual table definition.
        query = """
            SELECT
                ordinal_position,
                column_name,
                data_type,
                is_nullable,
                column_default,
                is_identity,
                identity_generation
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position;
        """

        # Execute the metadata query.
        cursor.execute(
            query,
            (
                TABLE_SCHEMA,
                TABLE_NAME,
            ),
        )

        # Fetch all columns.
        records = cursor.fetchall()

        # Display every column definition.
        for record in records:
            print(record)


# ============================================================================
# CONSTRAINTS
# ============================================================================

def inspect_constraints(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect primary key, unique, check, and foreign-key constraints.
    """

    print_section(
        "CONNECTOR VERSION CAPABILITY CONSTRAINTS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # pg_constraint contains the authoritative PostgreSQL constraint
        # definitions.
        query = """
            SELECT
                constraint_definition.conname AS constraint_name,
                constraint_definition.contype AS constraint_type,
                pg_get_constraintdef(
                    constraint_definition.oid
                ) AS constraint_definition
            FROM pg_constraint AS constraint_definition
            INNER JOIN pg_class AS table_definition
                ON table_definition.oid =
                   constraint_definition.conrelid
            INNER JOIN pg_namespace AS schema_definition
                ON schema_definition.oid =
                   table_definition.relnamespace
            WHERE schema_definition.nspname = %s
              AND table_definition.relname = %s
            ORDER BY
                constraint_definition.contype,
                constraint_definition.conname;
        """

        # Execute the read-only constraint query.
        cursor.execute(
            query,
            (
                TABLE_SCHEMA,
                TABLE_NAME,
            ),
        )

        # Fetch all constraints.
        records = cursor.fetchall()

        # Display every constraint.
        for record in records:
            print(record)


# ============================================================================
# EXISTING RECORDS
# ============================================================================

def inspect_existing_records(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect current capability assignments.

    This is particularly important because we already know that PostgreSQL
    connector version 3 currently has no assignments.
    """

    print_section(
        "EXISTING CONNECTOR VERSION CAPABILITY RECORDS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Retrieve existing records together with their capability names.
        query = """
            SELECT
                connector_version_capability.*,
                connector_capability.capability_code
            FROM conn.connector_version_capability
            INNER JOIN conn.connector_capability
                ON connector_capability.capability_id =
                   connector_version_capability.capability_id
            ORDER BY
                connector_version_capability.connector_version_id,
                connector_version_capability.capability_id;
        """

        # Execute the read-only query.
        cursor.execute(query)

        # Retrieve column names.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Retrieve records.
        records = cursor.fetchall()

        # Display the returned columns.
        print("Columns:")

        for column_name in column_names:
            print(f"  {column_name}")

        # Display records.
        print()
        print("Records:")

        if not records:
            print("  No connector capability assignments found.")
            return

        for record in records:
            print(record)


# ============================================================================
# FOREIGN KEY RELATIONSHIPS
# ============================================================================

def inspect_foreign_key_relationships(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect the exact foreign-key relationships of the association table.

    This confirms whether the table references:

        conn.connector_version

    and:

        conn.connector_capability
    """

    print_section(
        "CONNECTOR VERSION CAPABILITY FOREIGN KEYS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Inspect foreign keys owned by this association table.
        query = """
            SELECT
                source_column.attname AS source_column,
                target_schema.nspname AS target_schema,
                target_table.relname AS target_table,
                target_column.attname AS target_column,
                constraint_definition.conname AS constraint_name
            FROM pg_constraint AS constraint_definition

            INNER JOIN pg_class AS source_table
                ON source_table.oid =
                   constraint_definition.conrelid

            INNER JOIN pg_class AS target_table
                ON target_table.oid =
                   constraint_definition.confrelid

            INNER JOIN pg_attribute AS source_column
                ON source_column.attrelid =
                   constraint_definition.conrelid
               AND source_column.attnum =
                   constraint_definition.conkey[1]

            INNER JOIN pg_attribute AS target_column
                ON target_column.attrelid =
                   constraint_definition.confrelid
               AND target_column.attnum =
                   constraint_definition.confkey[1]

            INNER JOIN pg_namespace AS source_schema
                ON source_schema.oid =
                   source_table.relnamespace

            INNER JOIN pg_namespace AS target_schema
                ON target_schema.oid =
                   target_table.relnamespace

            WHERE constraint_definition.contype = 'f'
              AND source_schema.nspname = %s
              AND source_table.relname = %s

            ORDER BY
                source_column.attname;
        """

        # Execute the read-only query.
        cursor.execute(
            query,
            (
                TABLE_SCHEMA,
                TABLE_NAME,
            ),
        )

        # Fetch relationships.
        records = cursor.fetchall()

        # Display each relationship.
        for record in records:
            print(record)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Execute the complete read-only inspection.
    """

    # Display the overall inspection title.
    print_section(
        "CONNECTOR VERSION CAPABILITY STRUCTURE INSPECTION"
    )

    # Open the centralized metadata-store connection.
    with get_metastore_connection() as connection:

        # Inspect table columns.
        inspect_columns(connection)

        # Inspect all constraints.
        inspect_constraints(connection)

        # Inspect current records.
        inspect_existing_records(connection)

        # Inspect foreign-key relationships.
        inspect_foreign_key_relationships(connection)

    # Explicitly confirm that nothing was changed.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

# Execute main() only when this module is run directly.
if __name__ == "__main__":
    main()