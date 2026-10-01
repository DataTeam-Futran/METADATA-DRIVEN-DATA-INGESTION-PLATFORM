"""
Connector Capability Relationship Inspection

Purpose
-------
This script discovers how connector versions are associated with the
capability catalogue.

The metadata model already confirms that:

    conn.connector
        connector_id = 3
        platform_id  = 3
        connector_code = POSTGRESQL_CONNECTOR

and:

    conn.connector_capability

contains capability definitions such as:

    SCHEMA_DISCOVERY
    FULL_LOAD_SOURCE
    FULL_LOAD_TARGET
    BULK_READ
    BULK_WRITE

However, conn.connector_capability does not contain connector_id.

Therefore, this script discovers the actual relationship without assuming
the name of the association table.

IMPORTANT
---------
This script is completely READ-ONLY.

It does not:
- INSERT
- UPDATE
- DELETE
- CREATE
- ALTER
- DROP

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

# PostgreSQL connector ID already confirmed from conn.connector.
POSTGRESQL_CONNECTOR_ID = 3


# ============================================================================
# COMMON OUTPUT HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section header.

    This keeps the terminal output easy to read while we inspect the
    production metadata model.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# 1. FOREIGN KEYS OWNED BY connector_capability
# ============================================================================

def inspect_capability_foreign_keys(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect foreign keys defined on conn.connector_capability.

    IMPORTANT:
    ----------
    The previous version incorrectly used:

        constraint_name

    PostgreSQL stores the constraint name in:

        pg_constraint.conname

    Therefore this version correctly selects conname.
    """

    print_section(
        "FOREIGN KEYS OWNED BY conn.connector_capability"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # PostgreSQL system catalogs provide the authoritative definition
        # of foreign-key relationships.
        #
        # conkey/confkey are PostgreSQL arrays containing the source and
        # target column numbers for a constraint.
        #
        # We are currently interested in single-column relationships.
        query = """
            SELECT
                source_schema.nspname AS source_schema,
                source_table.relname AS source_table,
                source_column.attname AS source_column,
                target_schema.nspname AS target_schema,
                target_table.relname AS target_table,
                target_column.attname AS target_column,
                constraint_definition.conname AS constraint_name
            FROM pg_constraint AS constraint_definition

            INNER JOIN pg_class AS source_table
                ON source_table.oid = constraint_definition.conrelid

            INNER JOIN pg_class AS target_table
                ON target_table.oid = constraint_definition.confrelid

            INNER JOIN pg_attribute AS source_column
                ON source_column.attrelid = constraint_definition.conrelid
               AND source_column.attnum = constraint_definition.conkey[1]

            INNER JOIN pg_attribute AS target_column
                ON target_column.attrelid = constraint_definition.confrelid
               AND target_column.attnum = constraint_definition.confkey[1]

            INNER JOIN pg_namespace AS source_schema
                ON source_schema.oid = source_table.relnamespace

            INNER JOIN pg_namespace AS target_schema
                ON target_schema.oid = target_table.relnamespace

            WHERE constraint_definition.contype = 'f'
              AND source_schema.nspname = 'conn'
              AND source_table.relname = 'connector_capability'

            ORDER BY
                source_column.attname;
        """

        # Execute the read-only query.
        cursor.execute(query)

        # Retrieve all matching foreign keys.
        records = cursor.fetchall()

        # Display the result.
        if not records:
            print(
                "No foreign keys are defined directly on "
                "conn.connector_capability."
            )
            return

        # Print every relationship.
        for record in records:
            print(record)


# ============================================================================
# 2. TABLES REFERENCING connector_capability
# ============================================================================

def inspect_tables_referencing_capability(
    connection: psycopg.Connection,
) -> None:
    """
    Find tables that reference conn.connector_capability.

    This is particularly important because the association table is likely
    to reference:

        conn.connector_capability.capability_id

    The referencing table may contain connector_version_id as well.
    """

    print_section(
        "TABLES REFERENCING conn.connector_capability"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Find all foreign keys whose target is conn.connector_capability.
        query = """
            SELECT
                source_schema.nspname AS source_schema,
                source_table.relname AS source_table,
                source_column.attname AS source_column,
                target_schema.nspname AS target_schema,
                target_table.relname AS target_table,
                target_column.attname AS target_column,
                constraint_definition.conname AS constraint_name
            FROM pg_constraint AS constraint_definition

            INNER JOIN pg_class AS source_table
                ON source_table.oid = constraint_definition.conrelid

            INNER JOIN pg_class AS target_table
                ON target_table.oid = constraint_definition.confrelid

            INNER JOIN pg_attribute AS source_column
                ON source_column.attrelid = constraint_definition.conrelid
               AND source_column.attnum = constraint_definition.conkey[1]

            INNER JOIN pg_attribute AS target_column
                ON target_column.attrelid = constraint_definition.confrelid
               AND target_column.attnum = constraint_definition.confkey[1]

            INNER JOIN pg_namespace AS source_schema
                ON source_schema.oid = source_table.relnamespace

            INNER JOIN pg_namespace AS target_schema
                ON target_schema.oid = target_table.relnamespace

            WHERE constraint_definition.contype = 'f'
              AND target_schema.nspname = 'conn'
              AND target_table.relname = 'connector_capability'

            ORDER BY
                source_schema.nspname,
                source_table.relname,
                source_column.attname;
        """

        # Execute the read-only relationship query.
        cursor.execute(query)

        # Retrieve all relationships.
        records = cursor.fetchall()

        # Display the relationships.
        if not records:
            print(
                "No tables currently reference "
                "conn.connector_capability."
            )
            return

        # Print every discovered relationship.
        for record in records:
            print(record)


# ============================================================================
# 3. CONNECTOR/VERSION RELATED COLUMNS
# ============================================================================

def inspect_connector_version_related_tables(
    connection: psycopg.Connection,
) -> None:
    """
    Find conn-schema columns related to connector/version metadata.

    This helps identify possible association tables without assuming their
    names.
    """

    print_section(
        "CONNECTOR VERSION RELATED TABLES"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Search information_schema for connector/version related columns.
        query = """
            SELECT
                table_schema,
                table_name,
                column_name,
                data_type
            FROM information_schema.columns
            WHERE table_schema = 'conn'
              AND (
                    LOWER(column_name) LIKE '%connector%'
                    OR LOWER(column_name) LIKE '%version%'
                  )
            ORDER BY
                table_name,
                ordinal_position;
        """

        # Execute the read-only metadata query.
        cursor.execute(query)

        # Fetch matching columns.
        records = cursor.fetchall()

        # Print each matching table and column.
        for record in records:
            print(record)


# ============================================================================
# 4. POSSIBLE CAPABILITY ASSOCIATION TABLES
# ============================================================================

def inspect_capability_assignment_candidates(
    connection: psycopg.Connection,
) -> None:
    """
    Identify conn tables whose names suggest capability relationships.

    We do not assume a specific table name.

    The purpose is discovery only.
    """

    print_section(
        "POSSIBLE CONNECTOR CAPABILITY ASSOCIATION TABLES"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Find tables containing capability or connector in their names.
        query = """
            SELECT
                table_schema,
                table_name
            FROM information_schema.tables
            WHERE table_schema = 'conn'
              AND table_type = 'BASE TABLE'
              AND (
                    LOWER(table_name) LIKE '%capability%'
                    OR LOWER(table_name) LIKE '%connector%'
                  )
            ORDER BY
                table_name;
        """

        # Execute the table discovery query.
        cursor.execute(query)

        # Retrieve candidate tables.
        records = cursor.fetchall()

        # Print each candidate table.
        for record in records:
            print(record)


# ============================================================================
# 5. INSPECT POSTGRESQL CONNECTOR VERSIONS
# ============================================================================

def inspect_postgresql_connector_version(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect connector versions belonging to PostgreSQL connector 3.

    Connection 1 currently uses connector_version_id = 3.

    This inspection confirms the version metadata before we later associate
    runtime capabilities with the exact connector version.
    """

    print_section(
        "POSTGRESQL CONNECTOR VERSIONS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Retrieve all versions for PostgreSQL connector 3.
        query = """
            SELECT
                connector_version_id,
                connector_id,
                semantic_version,
                released_at,
                status_code,
                runtime_package,
                package_hash,
                min_runtime_version,
                max_runtime_version,
                created_at,
                created_by_principal_id,
                updated_at,
                updated_by_principal_id,
                row_version
            FROM conn.connector_version
            WHERE connector_id = %s
            ORDER BY connector_version_id;
        """

        # Execute the query using a parameterized connector ID.
        cursor.execute(
            query,
            (POSTGRESQL_CONNECTOR_ID,),
        )

        # Retrieve the records.
        records = cursor.fetchall()

        # Retrieve column names from the query result.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Display the column names.
        print("Columns:")

        for column_name in column_names:
            print(f"  {column_name}")

        # Display connector versions.
        print()
        print("Records:")

        if not records:
            print("  No PostgreSQL connector versions found.")
            return

        for record in records:
            print(record)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Execute all read-only connector capability inspections.
    """

    # Display the overall script title.
    print_section(
        "CONNECTOR CAPABILITY RELATIONSHIP INSPECTION"
    )

    # Open the centralized metadata-store connection.
    with get_metastore_connection() as connection:

        # Inspect foreign keys owned by connector_capability.
        inspect_capability_foreign_keys(connection)

        # Find tables that reference connector_capability.
        inspect_tables_referencing_capability(connection)

        # Find connector/version related columns.
        inspect_connector_version_related_tables(connection)

        # Find candidate capability association tables.
        inspect_capability_assignment_candidates(connection)

        # Inspect PostgreSQL connector versions.
        inspect_postgresql_connector_version(connection)

    # Confirm that the script performed no modifications.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

# Run main() only when this file is executed directly as a module.
if __name__ == "__main__":
    main()