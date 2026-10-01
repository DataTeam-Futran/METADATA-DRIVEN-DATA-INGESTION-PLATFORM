"""
Full Load Capability Metadata Inspection

Purpose
-------
Resolve the capability IDs required by the current Full Load POC.

Required capabilities:

    SCHEMA_DISCOVERY
    FULL_LOAD_SOURCE
    FULL_LOAD_TARGET

Why this inspection is needed
-----------------------------
The runtime should never assume capability IDs.

Instead, it should resolve them from:

    conn.connector_capability

using the stable capability_code.

The resolved capability IDs will later be used to create records in:

    conn.connector_version_capability

IMPORTANT
---------
This script is completely READ-ONLY.

No metadata is modified.
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

# PostgreSQL connector version currently used by the POC.
POSTGRESQL_CONNECTOR_VERSION_ID = 3

# Capability codes required for the Full Load POC.
REQUIRED_CAPABILITY_CODES = (
    "SCHEMA_DISCOVERY",
    "FULL_LOAD_SOURCE",
    "FULL_LOAD_TARGET",
)


# ============================================================================
# OUTPUT HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    This keeps the terminal output easy to read.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# INSPECT CAPABILITY DEFINITIONS
# ============================================================================

def inspect_capability_definitions(
    connection: psycopg.Connection,
) -> None:
    """
    Resolve the required capability definitions.

    The lookup uses capability_code rather than capability_id.

    This keeps the implementation metadata-driven.
    """

    print_section(
        "FULL LOAD CAPABILITY DEFINITIONS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Retrieve the required capability definitions.
        query = """
            SELECT
                capability_id,
                capability_code,
                category_code,
                value_type_code,
                description
            FROM conn.connector_capability
            WHERE capability_code = ANY(%s)
            ORDER BY capability_id;
        """

        # Execute the query using the required capability codes.
        cursor.execute(
            query,
            (
                list(REQUIRED_CAPABILITY_CODES),
            ),
        )

        # Fetch the matching capability definitions.
        records = cursor.fetchall()

        # Retrieve column names.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Print the column names.
        print("Columns:")

        for column_name in column_names:
            print(f"  {column_name}")

        # Print the capability definitions.
        print()
        print("Records:")

        for record in records:
            print(record)

        # Check whether any expected capability is missing.
        returned_codes = {
            record[1]
            for record in records
        }

        print()
        print("CAPABILITY VALIDATION:")

        for capability_code in REQUIRED_CAPABILITY_CODES:

            if capability_code in returned_codes:
                print(
                    f"{capability_code:<25} : FOUND"
                )
            else:
                print(
                    f"{capability_code:<25} : NOT FOUND"
                )


# ============================================================================
# CHECK EXISTING ASSIGNMENTS
# ============================================================================

def inspect_existing_assignments(
    connection: psycopg.Connection,
) -> None:
    """
    Check whether any of the required capabilities are already assigned
    to connector version 3.

    This confirms the current state before we perform the first metadata write.
    """

    print_section(
        "EXISTING FULL LOAD CAPABILITY ASSIGNMENTS"
    )

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Retrieve any existing assignments for the required capabilities.
        query = """
            SELECT
                connector_version_capability.connector_version_id,
                connector_version_capability.capability_id,
                connector_capability.capability_code,
                connector_version_capability.is_supported,
                connector_version_capability.capability_value
            FROM conn.connector_version_capability
            INNER JOIN conn.connector_capability
                ON connector_capability.capability_id =
                   connector_version_capability.capability_id
            WHERE connector_version_capability.connector_version_id = %s
              AND connector_capability.capability_code = ANY(%s)
            ORDER BY connector_capability.capability_code;
        """

        # Execute the read-only query.
        cursor.execute(
            query,
            (
                POSTGRESQL_CONNECTOR_VERSION_ID,
                list(REQUIRED_CAPABILITY_CODES),
            ),
        )

        # Retrieve existing assignments.
        records = cursor.fetchall()

        # Display the current state.
        if not records:
            print(
                "No required Full Load capabilities are currently assigned."
            )
            return

        # Print every existing assignment.
        for record in records:
            print(record)


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Execute the capability metadata inspection.
    """

    # Print the overall script title.
    print_section(
        "FULL LOAD CAPABILITY INSPECTION"
    )

    # Open the centralized metadata-store connection.
    with get_metastore_connection() as connection:

        # Resolve the required capability definitions.
        inspect_capability_definitions(connection)

        # Check current assignments for connector version 3.
        inspect_existing_assignments(connection)

    # Confirm that the script was read-only.
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