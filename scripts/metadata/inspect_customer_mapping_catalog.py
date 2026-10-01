"""
Customer Mapping Catalog Inspection
===================================

Purpose:
    Inspect the live mapping metadata model before creating a new
    source-to-target mapping for the Customer POC.

Why this is required:
    The metadata-driven platform must use the actual PostgreSQL
    metastore schema as the source of truth.

    We therefore inspect:
        1. Table columns
        2. Primary keys
        3. Foreign keys
        4. Unique constraints
        5. Check constraints
        6. Triggers
        7. Existing mapping examples
        8. Existing mapping versions
        9. Existing mapping source rows
       10. Existing mapping field rows
       11. Existing mapping field input rows

Important:
    This script is READ-ONLY.

    It does not INSERT, UPDATE or DELETE any metadata.
"""

# Import the PostgreSQL driver used by the project.
import psycopg

# Import the centralized metastore connection manager.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Mapping tables that are relevant to the Customer source-to-target mapping.
# ---------------------------------------------------------------------------
MAPPING_TABLES = [
    "mapping",
    "mapping_version",
    "mapping_source",
    "mapping_field",
    "mapping_field_input",
]


def print_separator(title: str) -> None:
    """
    Print a consistent section header.

    Why:
        A structured console output makes the inspection easier to review
        during development and troubleshooting.
    """

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def inspect_table_columns(connection: psycopg.Connection, table_name: str) -> None:
    """
    Display the actual columns of a mapping table.

    Why:
        We need to know which columns are required, nullable, identity-based,
        and whether PostgreSQL provides a default value.
    """

    print_separator(f"TABLE COLUMNS: map.{table_name}")

    query = """
        SELECT
            ordinal_position,
            column_name,
            data_type,
            is_nullable,
            column_default,
            identity_generation
        FROM information_schema.columns
        WHERE table_schema = 'map'
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        rows = cursor.fetchall()

    if not rows:
        print("No columns found.")
        return

    for row in rows:
        (
            ordinal_position,
            column_name,
            data_type,
            is_nullable,
            column_default,
            identity_generation,
        ) = row

        print(
            f"{ordinal_position:>2} | "
            f"{column_name:<35} | "
            f"{data_type:<25} | "
            f"nullable={is_nullable:<3} | "
            f"default={column_default} | "
            f"identity={identity_generation}"
        )


def inspect_constraints(
    connection: psycopg.Connection,
    table_name: str,
) -> None:
    """
    Display primary keys, unique constraints and check constraints.

    Why:
        Mapping metadata often has important business rules enforced by
        database constraints. We must understand them before inserting rows.
    """

    print_separator(f"CONSTRAINTS: map.{table_name}")

    query = """
        SELECT
            tc.constraint_name,
            tc.constraint_type,
            cc.check_clause
        FROM information_schema.table_constraints AS tc
        LEFT JOIN information_schema.check_constraints AS cc
            ON cc.constraint_schema = tc.constraint_schema
           AND cc.constraint_name = tc.constraint_name
        WHERE tc.table_schema = 'map'
          AND tc.table_name = %s
        ORDER BY
            tc.constraint_type,
            tc.constraint_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        rows = cursor.fetchall()

    if not rows:
        print("No constraints found.")
        return

    for constraint_name, constraint_type, check_clause in rows:
        print(
            f"{constraint_type:<20} | "
            f"{constraint_name:<50} | "
            f"{check_clause}"
        )


def inspect_foreign_keys(
    connection: psycopg.Connection,
    table_name: str,
) -> None:
    """
    Display foreign-key relationships for a mapping table.

    Why:
        This tells us exactly which catalog entities must already exist
        before we can create mapping metadata.
    """

    print_separator(f"FOREIGN KEYS: map.{table_name}")

    query = """
        SELECT
            tc.constraint_name,
            kcu.column_name,
            ccu.table_schema AS referenced_schema,
            ccu.table_name AS referenced_table,
            ccu.column_name AS referenced_column
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.constraint_schema = kcu.constraint_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON tc.constraint_name = ccu.constraint_name
           AND tc.constraint_schema = ccu.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'map'
          AND tc.table_name = %s
        ORDER BY tc.constraint_name, kcu.ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        rows = cursor.fetchall()

    if not rows:
        print("No foreign keys found.")
        return

    for row in rows:
        (
            constraint_name,
            column_name,
            referenced_schema,
            referenced_table,
            referenced_column,
        ) = row

        print(
            f"{constraint_name:<45} | "
            f"{column_name:<30} → "
            f"{referenced_schema}.{referenced_table}.{referenced_column}"
        )


def inspect_triggers(
    connection: psycopg.Connection,
    table_name: str,
) -> None:
    """
    Display triggers attached to the mapping table.

    Why:
        Audit fields may be populated automatically by PostgreSQL triggers.
        We must avoid manually inserting values that the database owns.
    """

    print_separator(f"TRIGGERS: map.{table_name}")

    query = """
        SELECT
            trigger_name,
            event_manipulation,
            action_timing,
            action_statement
        FROM information_schema.triggers
        WHERE event_object_schema = 'map'
          AND event_object_table = %s
        ORDER BY trigger_name, event_manipulation;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        rows = cursor.fetchall()

    if not rows:
        print("No triggers found.")
        return

    for row in rows:
        (
            trigger_name,
            event_manipulation,
            action_timing,
            action_statement,
        ) = row

        print(
            f"{trigger_name:<45} | "
            f"{action_timing:<10} | "
            f"{event_manipulation:<10} | "
            f"{action_statement}"
        )


def inspect_existing_rows(
    connection: psycopg.Connection,
    table_name: str,
) -> None:
    """
    Display existing mapping metadata examples.

    Why:
        Existing records help us understand the actual value conventions
        used by the live metastore, such as status codes and mapping types.

    Security:
        Only metadata is displayed. No credentials or secret references
        are queried.
    """

    print_separator(f"EXISTING DATA: map.{table_name}")

    query = f"""
        SELECT *
        FROM map.{table_name}
        ORDER BY 1
        LIMIT 20;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

        # Read column names directly from the cursor description so the
        # output remains useful if the schema evolves.
        column_names = [
            description.name
            for description in cursor.description
        ]

    if not rows:
        print("No rows found.")
        return

    print("Columns:")
    print(" | ".join(column_names))
    print("-" * 80)

    for row in rows:
        print(" | ".join(str(value) for value in row))


def main() -> None:
    """
    Execute the complete read-only mapping metadata inspection.

    Why:
        This gives us one consolidated view of the live mapping model
        before any Customer mapping records are inserted.
    """

    print("=" * 80)
    print("CUSTOMER MAPPING CATALOG INSPECTION")
    print("=" * 80)

    # Open a transaction-safe read connection to the metadata database.
    with get_metastore_connection() as connection:

        # Inspect each mapping table individually.
        for table_name in MAPPING_TABLES:
            inspect_table_columns(connection, table_name)
            inspect_constraints(connection, table_name)
            inspect_foreign_keys(connection, table_name)
            inspect_triggers(connection, table_name)
            inspect_existing_rows(connection, table_name)

    print()
    print("=" * 80)
    print("MAPPING CATALOG INSPECTION COMPLETED")
    print("=" * 80)
    print("No metadata was modified.")


# Execute the inspection only when this file is run as a module/script.
if __name__ == "__main__":
    main()