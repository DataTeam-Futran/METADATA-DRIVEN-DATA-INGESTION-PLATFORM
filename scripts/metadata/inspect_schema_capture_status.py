"""
Schema Capture Status Inspection

Purpose:
    Inspect the CHECK constraints and status-related metadata for
    catalog.schema_capture_run.

Why:
    status_code is mandatory and has no default value.
    Before inserting the first schema capture record, we need to use
    the values permitted by the database design.

Important:
    This script is completely READ-ONLY.
"""

# Import os to read database configuration from the environment.
import os

# Import psycopg for PostgreSQL connectivity.
import psycopg

# Import load_dotenv to load the project's .env file.
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    """
    Create a metadata database connection using environment variables.
    """

    # Load variables from the project's .env file.
    load_dotenv()

    # Connect to the metadata/control database.
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


def inspect_constraints(connection: psycopg.Connection) -> None:
    """
    Display the actual PostgreSQL constraint definitions for
    catalog.schema_capture_run.
    """

    # Read the PostgreSQL system catalog to obtain the real constraint
    # expressions rather than guessing allowed values.
    query = """
        SELECT
            con.conname AS constraint_name,
            pg_get_constraintdef(con.oid) AS constraint_definition
        FROM pg_constraint AS con
        INNER JOIN pg_class AS cls
            ON cls.oid = con.conrelid
        INNER JOIN pg_namespace AS ns
            ON ns.oid = cls.relnamespace
        WHERE ns.nspname = 'catalog'
          AND cls.relname = 'schema_capture_run'
          AND con.contype = 'c'
        ORDER BY con.conname;
    """

    # Execute the read-only query.
    with connection.cursor() as cursor:
        cursor.execute(query)

        # Fetch all CHECK constraints.
        rows = cursor.fetchall()

    # Display the constraint definitions.
    print("=" * 100)
    print("SCHEMA CAPTURE RUN CHECK CONSTRAINTS")
    print("=" * 100)

    for row in rows:
        print(f"{row[0]} | {row[1]}")

    # Explicitly report if no CHECK constraints were found.
    if not rows:
        print("No CHECK constraints were found.")


def main() -> None:
    """
    Execute the status/check inspection.
    """

    # Open the metadata database connection.
    connection = get_connection()

    try:
        # Inspect the actual database constraints.
        inspect_constraints(connection)

    finally:
        # Always close the database connection.
        connection.close()

    # Confirm that the database was not modified.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# Run the inspection when this module is executed directly.
if __name__ == "__main__":
    main()