"""
PostgreSQL Connector -> Platform -> Datatype Metadata Inspection

Purpose
-------
This script performs a READ-ONLY inspection of the metadata relationships
required for PostgreSQL schema capture.

The inspection verifies:

1. PostgreSQL connector metadata.
2. PostgreSQL database platform metadata.
3. Connector capability metadata.
4. PostgreSQL native datatype metadata.

Why this script is needed
-------------------------
Before implementing schema capture, the ingestion runtime must know:

    Dynamic Connection
            |
            v
    Connector
            |
            v
    Database Platform
            |
            v
    Native Datatypes

The script deliberately inspects the actual database structure instead of
assuming column names. This is important because the metadata model contains
many normalized tables and their relationships should be discovered from the
database itself.

IMPORTANT
---------
This script is READ-ONLY.

It does NOT:
- create metadata
- update metadata
- delete metadata
- modify source data
- modify target data
- create schema versions
- create dataset fields

It only reads metadata from the metastore database.
"""

# ---------------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------------

# PostgreSQL driver used to connect to the metadata store.
import psycopg

# ---------------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------------

# Centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ===========================================================================
# CONSTANTS
# ===========================================================================

# Connector ID for the PostgreSQL connector.
#
# This value is currently known from the metadata inspection performed during
# the POC. It identifies conn.connector.connector_id.
POSTGRESQL_CONNECTOR_ID = 3

# PostgreSQL platform ID.
#
# This value is also confirmed from conn.connector.platform_id.
POSTGRESQL_PLATFORM_ID = 3


# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section header.

    Why:
    ----
    The inspection output is intentionally verbose because it is used during
    development and troubleshooting. Consistent headers make the terminal
    output easier to review and share.
    """

    print("=" * 100)
    print(title)
    print("=" * 100)


def print_columns(columns: list[str]) -> None:
    """
    Print database column names in a readable format.

    Parameters
    ----------
    columns:
        List of column names returned by PostgreSQL.
    """

    print("Columns:")

    # Print every column returned by the database.
    for column_name in columns:
        print(f"  {column_name}")


def print_records(
    records: list[tuple],
    column_names: list[str],
) -> None:
    """
    Print database records in a simple readable format.

    Parameters
    ----------
    records:
        Rows returned from PostgreSQL.

    column_names:
        Column names corresponding to each row.
    """

    print()
    print("Record Columns:")

    # Display the column names returned by PostgreSQL.
    for column_name in column_names:
        print(f"  {column_name}")

    print()
    print("Records:")

    # Handle the case where the table contains no rows.
    if not records:
        print("  No records found.")
        return

    # Print each database row exactly as returned.
    for record in records:
        print(record)


# ===========================================================================
# CONNECTOR INSPECTION
# ===========================================================================

def inspect_postgresql_connector(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect the PostgreSQL connector definition.

    Important relationship
    ----------------------
    conn.connector contains platform_id directly.

    Therefore the platform should NOT be derived from
    conn.connector_version.

    Current relationship:

        connector_id = 3
              |
              v
        platform_id = 3
              |
              v
        POSTGRESQL platform
    """

    print_section("POSTGRESQL CONNECTOR")

    # Open a cursor for the read-only metadata query.
    with connection.cursor() as cursor:

        # Select the PostgreSQL connector using its metadata identifier.
        query = """
            SELECT
                connector_id,
                connector_code,
                connector_name,
                platform_id,
                category_code,
                runtime_class,
                driver_family,
                supports_source,
                supports_target,
                status_code,
                created_at,
                created_by_principal_id,
                updated_at,
                updated_by_principal_id,
                row_version
            FROM conn.connector
            WHERE connector_id = %s;
        """

        # Execute the query using a parameter instead of string interpolation.
        cursor.execute(
            query,
            (POSTGRESQL_CONNECTOR_ID,),
        )

        # Fetch the connector record.
        record = cursor.fetchone()

        # Handle an unexpected missing connector.
        if record is None:
            print("PostgreSQL connector was not found.")
            return

        # Read the column names returned by PostgreSQL.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Print the connector definition.
        print_columns(column_names)

        print()
        print("Record:")
        print(record)


# ===========================================================================
# DATABASE PLATFORM INSPECTION
# ===========================================================================

def inspect_postgresql_platform(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect the PostgreSQL database platform.

    Why:
    ----
    dtype.native_datatype is associated with a database platform.
    Therefore schema capture needs the platform identity before resolving
    physical source datatypes.
    """

    print_section("POSTGRESQL DATABASE PLATFORM")

    # Open a cursor for the read-only metadata query.
    with connection.cursor() as cursor:

        # Retrieve the PostgreSQL platform definition.
        query = """
            SELECT
                platform_id,
                platform_code,
                vendor_name,
                product_name,
                category_code,
                official_doc_url,
                status_code,
                created_at,
                created_by_principal_id,
                updated_at,
                updated_by_principal_id,
                row_version
            FROM conn.database_platform
            WHERE platform_id = %s;
        """

        # Execute the query with the known PostgreSQL platform ID.
        cursor.execute(
            query,
            (POSTGRESQL_PLATFORM_ID,),
        )

        # Fetch the platform record.
        record = cursor.fetchone()

        # Handle missing platform metadata.
        if record is None:
            print("PostgreSQL database platform was not found.")
            return

        # Get the returned column names.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Print the platform metadata.
        print_columns(column_names)

        print()
        print("Record:")
        print(record)


# ===========================================================================
# CONNECTOR CAPABILITY INSPECTION
# ===========================================================================

def inspect_connector_capabilities(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect conn.connector_capability without assuming its column structure.

    Why:
    ----
    The earlier inspection incorrectly assumed that this table contained
    connector_id.

    PostgreSQL reported:

        column "connector_id" does not exist

    Instead of guessing the relationship, this function first discovers the
    actual table columns and then retrieves a limited sample using SELECT *.

    This makes the inspection safe and prevents us from implementing the
    wrong metadata relationship.
    """

    print_section("CONNECTOR CAPABILITY METADATA")

    # Open a cursor for the metadata inspection.
    with connection.cursor() as cursor:

        # -------------------------------------------------------------------
        # Step 1: Discover the actual table columns.
        # -------------------------------------------------------------------
        #
        # We inspect information_schema first because we do not want to
        # assume that conn.connector_capability contains connector_id.
        columns_query = """
            SELECT
                column_name
            FROM information_schema.columns
            WHERE table_schema = 'conn'
              AND table_name = 'connector_capability'
            ORDER BY ordinal_position;
        """

        # Execute the read-only column inspection.
        cursor.execute(columns_query)

        # Fetch all column names.
        columns = cursor.fetchall()

        # Display the actual table structure.
        print_columns(
            [
                row[0]
                for row in columns
            ]
        )

        # -------------------------------------------------------------------
        # Step 2: Retrieve a limited sample of capability records.
        # -------------------------------------------------------------------
        #
        # SELECT * is intentionally used here because the purpose of this
        # function is to discover the actual structure of the table.
        #
        # LIMIT 50 prevents excessive terminal output if the table contains
        # many capability records.
        records_query = """
            SELECT *
            FROM conn.connector_capability
            ORDER BY 1
            LIMIT 50;
        """

        # Execute the read-only capability query.
        cursor.execute(records_query)

        # Capture the actual column names returned by SELECT *.
        record_column_names = [
            description.name
            for description in cursor.description
        ]

        # Fetch the capability records.
        records = cursor.fetchall()

        # Print the records and their actual columns.
        print_records(
            records,
            record_column_names,
        )


# ===========================================================================
# NATIVE DATATYPE INSPECTION
# ===========================================================================

def inspect_postgresql_native_datatypes(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect PostgreSQL native datatypes from dtype.native_datatype.

    Why:
    ----
    During schema capture, physical source datatypes such as:

        integer
        character varying

    must be resolved to metadata IDs.

    We must NOT hardcode values such as:

        integer            -> 62
        character varying -> 73

    Instead, the runtime should resolve these values from the dtype metadata
    using the PostgreSQL platform.

    This inspection helps verify the metadata required for that resolution.
    """

    print_section("POSTGRESQL NATIVE DATATYPES")

    # Open a cursor for the datatype metadata query.
    with connection.cursor() as cursor:

        # Retrieve active PostgreSQL native datatype definitions.
        query = """
            SELECT
                native_datatype_id,
                platform_id,
                database_version_id,
                canonical_datatype_id,
                native_type_name,
                category_code,
                supports_length,
                supports_precision,
                supports_scale,
                min_length,
                max_length,
                min_precision,
                max_precision,
                min_scale,
                max_scale,
                is_unicode,
                is_signed,
                timezone_semantics_code,
                is_lob,
                is_complex,
                status_code
            FROM dtype.native_datatype
            WHERE platform_id = %s
              AND status_code = 'ACTIVE'
            ORDER BY native_datatype_id;
        """

        # Execute the query using the PostgreSQL platform ID.
        cursor.execute(
            query,
            (POSTGRESQL_PLATFORM_ID,),
        )

        # Fetch all active PostgreSQL native datatypes.
        records = cursor.fetchall()

        # Capture the returned column names.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Print the metadata records.
        print_records(
            records,
            column_names,
        )


# ===========================================================================
# IMPORTANT DATATYPE LOOKUP
# ===========================================================================

def inspect_required_postgresql_datatypes(
    connection: psycopg.Connection,
) -> None:
    """
    Verify the specific datatypes currently used by the POC source.

    Current physical source:

        demo_source_db.public.customer

    contains:

        customer_id       -> integer
        customer_name     -> character varying
        email             -> character varying
        city              -> character varying

    This function confirms how those physical datatype names map to
    dtype.native_datatype.

    The query uses native_type_name rather than hardcoded datatype IDs.
    """

    print_section("REQUIRED CUSTOMER SOURCE DATATYPE RESOLUTION")

    # Open a read-only cursor.
    with connection.cursor() as cursor:

        # Resolve the two physical datatype names used by customer.
        query = """
            SELECT
                native_datatype_id,
                platform_id,
                database_version_id,
                canonical_datatype_id,
                native_type_name,
                category_code,
                supports_length,
                supports_precision,
                supports_scale,
                status_code
            FROM dtype.native_datatype
            WHERE platform_id = %s
              AND status_code = 'ACTIVE'
              AND LOWER(native_type_name) IN (
                    'integer',
                    'character varying'
              )
            ORDER BY native_type_name;
        """

        # Execute the datatype lookup dynamically by platform.
        cursor.execute(
            query,
            (POSTGRESQL_PLATFORM_ID,),
        )

        # Retrieve matching datatype metadata.
        records = cursor.fetchall()

        # Retrieve returned column names.
        column_names = [
            description.name
            for description in cursor.description
        ]

        # Print the resolved datatype metadata.
        print_records(
            records,
            column_names,
        )


# ===========================================================================
# MAIN
# ===========================================================================

def main() -> None:
    """
    Execute all PostgreSQL platform and datatype metadata inspections.

    The connection is managed by app.db.metastore, which centralizes the
    metadata-store connection configuration.

    This script intentionally performs no INSERT, UPDATE, DELETE, DDL, or
    transaction commit operations.
    """

    # Print the overall script title.
    print()
    print("=" * 100)
    print("POSTGRESQL PLATFORM AND DATATYPE METADATA INSPECTION")
    print("=" * 100)
    print()

    # Open the metadata-store connection using the application's standard
    # connection manager.
    with get_metastore_connection() as connection:

        # Inspect the PostgreSQL connector definition.
        inspect_postgresql_connector(connection)

        # Inspect the PostgreSQL database platform.
        inspect_postgresql_platform(connection)

        # Inspect the actual connector capability table structure.
        inspect_connector_capabilities(connection)

        # Inspect all active PostgreSQL native datatypes.
        inspect_postgresql_native_datatypes(connection)

        # Inspect specifically the datatypes required by the customer POC.
        inspect_required_postgresql_datatypes(connection)

    # Confirm that this script only inspected metadata.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# ===========================================================================
# SCRIPT ENTRY POINT
# ===========================================================================

# Execute main() only when this file is run as a Python module/script.
#
# This allows the functions above to be imported by other code without
# automatically executing the inspection.
if __name__ == "__main__":
    main()