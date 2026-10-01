"""
Catalog ID Generation Inspection

Purpose:
    Determine how the catalog schema-capture tables generate their primary
    key IDs.

Tables inspected:
    - catalog.schema_capture_run
    - catalog.dataset_schema_version
    - catalog.dataset_field

Why this is required:
    The previous inspection showed that these ID columns have no default
    value and no PostgreSQL sequence was found.

    Before inserting metadata, we need to identify whether the platform
    expects:
        - application-generated IDs,
        - UUID-derived IDs,
        - a shared ID service,
        - trigger-based generation,
        - or another metadata mechanism.

Important:
    This script is READ-ONLY.
    It does not insert, update, or delete any data.
"""

# Import os so database configuration can be loaded from the environment.
import os

# Import psycopg for PostgreSQL connectivity.
import psycopg

# Import load_dotenv to load the existing project .env file.
from dotenv import load_dotenv


def get_connection() -> psycopg.Connection:
    """
    Create a connection to the metadata/control database.

    Credentials are read from the existing environment configuration.
    No credentials are hardcoded in this script.
    """

    # Load variables from the project's .env file.
    load_dotenv()

    # Open the metadata database connection.
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


def inspect_identity_and_generation(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect identity, generated, and default properties of the three
    schema-capture primary-key columns.
    """

    # Query PostgreSQL's information_schema for the relevant columns.
    query = """
        SELECT
            table_schema,
            table_name,
            column_name,
            data_type,
            column_default,
            is_identity,
            identity_generation,
            is_generated
        FROM information_schema.columns
        WHERE table_schema = 'catalog'
          AND (
                (table_name = 'schema_capture_run'
                 AND column_name = 'schema_capture_run_id')
                OR
                (table_name = 'dataset_schema_version'
                 AND column_name = 'schema_version_id')
                OR
                (table_name = 'dataset_field'
                 AND column_name = 'field_id')
          )
        ORDER BY table_name, column_name;
    """

    # Execute the read-only metadata query.
    with connection.cursor() as cursor:
        cursor.execute(query)

        # Fetch all matching primary-key definitions.
        rows = cursor.fetchall()

    # Print the results in a readable format.
    print("=" * 100)
    print("CATALOG PRIMARY KEY GENERATION")
    print("=" * 100)

    print(
        f"{'Table':<35}"
        f"{'Column':<35}"
        f"{'Default':<30}"
        f"{'Identity':<12}"
        f"{'Generated':<12}"
    )

    # Display every discovered property.
    for row in rows:
        print(
            f"{row[1]:<35}"
            f"{row[2]:<35}"
            f"{str(row[4]):<30}"
            f"{str(row[5]):<12}"
            f"{str(row[7]):<12}"
        )


def inspect_triggers(
    connection: psycopg.Connection,
) -> None:
    """
    Inspect triggers defined on the three schema-capture tables.

    A trigger may be responsible for assigning primary-key values.
    """

    # Query PostgreSQL for triggers on the catalog tables.
    query = """
        SELECT
            event_object_schema,
            event_object_table,
            trigger_name,
            action_statement
        FROM information_schema.triggers
        WHERE event_object_schema = 'catalog'
          AND event_object_table IN (
                'schema_capture_run',
                'dataset_schema_version',
                'dataset_field'
          )
        ORDER BY
            event_object_table,
            trigger_name;
    """

    # Execute the trigger inspection query.
    with connection.cursor() as cursor:
        cursor.execute(query)

        # Fetch all matching triggers.
        rows = cursor.fetchall()

    # Print the trigger information.
    print()
    print("=" * 100)
    print("CATALOG TRIGGERS")
    print("=" * 100)

    # Display every trigger found.
    for row in rows:
        print(
            f"Table   : {row[1]}"
        )
        print(
            f"Trigger : {row[2]}"
        )
        print(
            f"Action  : {row[3]}"
        )
        print("-" * 100
        )

    # Explicitly report when no triggers exist.
    if not rows:
        print("No triggers found on the schema-capture tables.")


def inspect_functions(
    connection: psycopg.Connection,
) -> None:
    """
    Look for functions/procedures whose names indicate ID generation.

    This is an additional read-only check for platform-level ID generation.
    """

    # Search PostgreSQL functions for likely ID-generation names.
    query = """
        SELECT
            n.nspname AS schema_name,
            p.proname AS function_name
        FROM pg_proc AS p
        INNER JOIN pg_namespace AS n
            ON n.oid = p.pronamespace
        WHERE n.nspname IN (
            'catalog',
            'runtime',
            'sec',
            'conn'
        )
          AND (
                p.proname ILIKE '%id%'
                OR p.proname ILIKE '%sequence%'
                OR p.proname ILIKE '%generate%'
                OR p.proname ILIKE '%next%'
          )
        ORDER BY
            n.nspname,
            p.proname;
    """

    # Execute the function inspection query.
    with connection.cursor() as cursor:
        cursor.execute(query)

        # Fetch all matching functions.
        rows = cursor.fetchall()

    # Display possible ID-generation functions.
    print()
    print("=" * 100)
    print("POSSIBLE ID GENERATION FUNCTIONS")
    print("=" * 100)

    # Print every candidate function.
    for row in rows:
        print(
            f"{row[0]} | {row[1]}"
        )

    # Report when no candidates were found.
    if not rows:
        print("No possible ID-generation functions were found.")


def main() -> None:
    """
    Execute all read-only ID-generation inspections.
    """

    # Open the metadata database connection.
    connection = get_connection()

    try:
        # Inspect primary-key generation behavior.
        inspect_identity_and_generation(connection)

        # Inspect table triggers.
        inspect_triggers(connection)

        # Inspect possible ID-generation functions.
        inspect_functions(connection)

    finally:
        # Always close the database connection.
        connection.close()

    # Confirm that this script did not change metadata.
    print()
    print("=" * 100)
    print("INSPECTION COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


# Run the inspection when this module is executed directly.
if __name__ == "__main__":
    main()