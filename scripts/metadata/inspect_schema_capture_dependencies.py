"""
Schema Capture Dependency Inspection

Purpose:
    Inspect the exact PostgreSQL sequences used by the catalog schema-capture
    tables and inspect the exact columns of dtype.native_datatype.

Why this script exists:
    The schema-capture implementation must use the real database metadata.
    We do not want to guess sequence names or datatype column names.

Important:
    This script is completely READ-ONLY.
    It does not INSERT, UPDATE, DELETE, or otherwise modify metadata.
"""

# Import os so that database connection settings can be read from .env.
import os

# Import psycopg for the PostgreSQL connection.
import psycopg

# Import load_dotenv so the existing project .env file is loaded.
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    """
    Create a connection to the metadata/control database.

    The credentials are read from the existing environment configuration.
    No password is hardcoded in this script.
    """

    # Load environment variables from the project's .env file.
    load_dotenv()

    # Create and return the PostgreSQL metadata-store connection.
    return psycopg.connect(
        host=os.getenv("MDIP_METASTORE_HOST"),
        port=os.getenv("MDIP_METASTORE_PORT"),
        dbname=os.getenv("MDIP_METASTORE_DATABASE"),
        user=os.getenv("MDIP_METASTORE_USERNAME"),
        password=os.getenv("MDIP_METASTORE_PASSWORD"),
        sslmode=os.getenv(
            "MDIP_METASTORE_SSLMODE",
            "disable",
        ),
    )


def inspect_sequences(connection: psycopg.Connection) -> None:
    """
    Display sequences related to schema capture metadata.

    We need this because the catalog ID columns currently do not have
    column defaults, so the application must know how IDs are generated.
    """

    # Query PostgreSQL's information_schema for catalog sequences.
    query = """
        SELECT
            sequence_schema,
            sequence_name
        FROM information_schema.sequences
        WHERE sequence_schema = 'catalog'
          AND (
                sequence_name ILIKE '%schema_capture%'
                OR sequence_name ILIKE '%schema_version%'
                OR sequence_name ILIKE '%dataset_field%'
          )
        ORDER BY sequence_name;
    """

    # Create a cursor for the read-only query.
    with connection.cursor() as cursor:

        # Execute the sequence inspection query.
        cursor.execute(query)

        # Fetch all matching sequences.
        rows = cursor.fetchall()

    # Print a clear section heading.
    print("=" * 80)
    print("CATALOG SCHEMA CAPTURE SEQUENCES")
    print("=" * 80)

    # Display each sequence returned by PostgreSQL.
    for row in rows:
        print(
            f"{row[0]} | {row[1]}"
        )

    # Report when PostgreSQL returned no matching sequences.
    if not rows:
        print("No matching catalog sequences were found.")


def inspect_native_datatype(
    connection: psycopg.Connection,
) -> None:
    """
    Display the exact columns of dtype.native_datatype.

    This prevents the application from making assumptions about the
    datatype catalogue structure.
    """

    # Query PostgreSQL metadata for the native datatype table.
    query = """
        SELECT
            ordinal_position,
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = 'dtype'
          AND table_name = 'native_datatype'
        ORDER BY ordinal_position;
    """

    # Create a cursor for the read-only query.
    with connection.cursor() as cursor:

        # Execute the datatype metadata query.
        cursor.execute(query)

        # Fetch all table columns.
        rows = cursor.fetchall()

    # Print a clear section heading.
    print()
    print("=" * 80)
    print("DTYPE.NATIVE_DATATYPE COLUMNS")
    print("=" * 80)

    # Print a readable column listing.
    print(
        f"{'Ordinal':<10}"
        f"{'Column':<40}"
        f"{'Data Type':<25}"
    )

    # Display every column in ordinal order.
    for row in rows:
        print(
            f"{str(row[0]):<10}"
            f"{str(row[1]):<40}"
            f"{str(row[2]):<25}"
        )

    # Report when no columns were found.
    if not rows:
        print("No columns were found.")


def main() -> None:
    """
    Run both read-only metadata inspections.
    """

    # Open the metadata-store connection.
    connection = get_connection()

    try:
        # Inspect catalog sequence definitions.
        inspect_sequences(connection)

        # Inspect the native datatype table structure.
        inspect_native_datatype(connection)

    finally:
        # Always close the PostgreSQL connection.
        connection.close()

    # Confirm that no metadata was modified.
    print()
    print("=" * 80)
    print("INSPECTION COMPLETE")
    print("=" * 80)
    print("No metadata was modified.")


# Execute the inspection when the module is run directly.
if __name__ == "__main__":
    main()