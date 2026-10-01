"""
PostgreSQL Connector Version Capability Inspection

Purpose
-------
This script resolves the capabilities assigned to the active PostgreSQL
connector version.

Metadata relationship:

    conn.connector
            |
            | connector_id
            v
    conn.connector_version
            |
            | connector_version_id
            v
    conn.connector_version_capability
            |
            | capability_id
            v
    conn.connector_capability

For the current POC:

    connector_id         = 3
    connector_version_id = 3

This script is READ-ONLY.

No metadata is inserted, updated, deleted, or otherwise modified.
"""

# ============================================================================
# IMPORTS
# ============================================================================

# PostgreSQL driver used for the connection type hint.
import psycopg

# Centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ============================================================================
# CONSTANTS
# ============================================================================

# PostgreSQL connector ID already confirmed from conn.connector.
POSTGRESQL_CONNECTOR_ID = 3

# PostgreSQL connector version currently used by Connection 1.
POSTGRESQL_CONNECTOR_VERSION_ID = 3


# ============================================================================
# HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a standard section header.

    This keeps the inspection output easy to read.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# INSPECT CONNECTOR VERSION CAPABILITIES
# ============================================================================

def inspect_connector_version_capabilities(
    connection: psycopg.Connection,
) -> None:
    """
    Resolve all capabilities assigned to PostgreSQL connector version 3.

    The query joins:

        connector_version_capability
                    |
                    +--> connector_capability

    This gives us the actual capabilities supported by the runtime version.
    """

    print_section(
        "POSTGRESQL CONNECTOR VERSION CAPABILITIES"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Resolve the capabilities assigned to connector version 3.
        #
        # We also join connector_version and connector so the result proves
        # that the capabilities belong to the expected PostgreSQL connector.
        query = """
            SELECT
                connector.connector_id,
                connector.connector_code,
                connector_version.connector_version_id,
                connector_version.semantic_version,
                connector_capability.capability_id,
                connector_capability.capability_code,
                connector_capability.category_code,
                connector_capability.value_type_code,
                connector_capability.description
            FROM conn.connector_version_capability
            INNER JOIN conn.connector_version
                ON connector_version.connector_version_id =
                   connector_version_capability.connector_version_id
            INNER JOIN conn.connector
                ON connector.connector_id =
                   connector_version.connector_id
            INNER JOIN conn.connector_capability
                ON connector_capability.capability_id =
                   connector_version_capability.capability_id
            WHERE connector.connector_id = %s
              AND connector_version.connector_version_id = %s
            ORDER BY
                connector_capability.category_code,
                connector_capability.capability_code;
        """

        # Execute the read-only query using parameters.
        cursor.execute(
            query,
            (
                POSTGRESQL_CONNECTOR_ID,
                POSTGRESQL_CONNECTOR_VERSION_ID,
            ),
        )

        # Retrieve all capability assignments.
        records = cursor.fetchall()

        # Retrieve column names returned by PostgreSQL.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Display column names.
        print("Columns:")

        for column_name in column_names:
            print(f"  {column_name}")

        # Display capability records.
        print()
        print("Records:")

        if not records:
            print(
                "No capabilities are assigned to PostgreSQL "
                "connector version 3."
            )
            return

        for record in records:
            print(record)


# ============================================================================
# CHECK REQUIRED FULL-LOAD CAPABILITIES
# ============================================================================

def inspect_required_full_load_capabilities(
    connection: psycopg.Connection,
) -> None:
    """
    Check whether the PostgreSQL connector version has the capabilities
    required for the first Full Load POC.

    Required capabilities:

        SCHEMA_DISCOVERY
        FULL_LOAD_SOURCE
        FULL_LOAD_TARGET

    Why:
    ----
    Our Full Load pipeline needs to:

        1. Discover source schema.
        2. Read source data.
        3. Write data to the target.

    This check is still READ-ONLY. It does not execute the load.
    """

    print_section(
        "REQUIRED FULL-LOAD CAPABILITY CHECK"
    )

    # These are the capabilities required for our current POC.
    required_capabilities = (
        "SCHEMA_DISCOVERY",
        "FULL_LOAD_SOURCE",
        "FULL_LOAD_TARGET",
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Count how many of the required capabilities are assigned to
        # connector version 3.
        query = """
            SELECT
                capability_code
            FROM conn.connector_version_capability
            INNER JOIN conn.connector_capability
                ON connector_capability.capability_id =
                   connector_version_capability.capability_id
            WHERE connector_version_capability.connector_version_id = %s
              AND capability_code = ANY(%s)
            ORDER BY capability_code;
        """

        # Execute the query with the required capability list.
        cursor.execute(
            query,
            (
                POSTGRESQL_CONNECTOR_VERSION_ID,
                list(required_capabilities),
            ),
        )

        # Retrieve assigned required capabilities.
        records = cursor.fetchall()

        # Convert database rows into a set for simple membership checking.
        available_capabilities = {
            record[0]
            for record in records
        }

        # Display each required capability and whether it is assigned.
        for capability in required_capabilities:

            # Determine whether the capability exists for this connector
            # version.
            is_available = capability in available_capabilities

            print(
                f"{capability:<25} : "
                f"{'AVAILABLE' if is_available else 'NOT AVAILABLE'}"
            )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Execute the PostgreSQL connector capability inspection.

    All operations are read-only.
    """

    # Print the overall script title.
    print_section(
        "POSTGRESQL CONNECTOR CAPABILITY INSPECTION"
    )

    # Open the centralized metadata-store connection.
    with get_metastore_connection() as connection:

        # Inspect every capability assigned to connector version 3.
        inspect_connector_version_capabilities(connection)

        # Check the capabilities required for Full Load.
        inspect_required_full_load_capabilities(connection)

    # Explicitly confirm that nothing was modified.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

# Run main() only when this module is executed directly.
if __name__ == "__main__":
    main()