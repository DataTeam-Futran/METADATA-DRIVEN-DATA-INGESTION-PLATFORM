"""
Inspect Dynamic Customer Source
===============================

This script inspects the physical CUSTOMER table discovered through
the dynamically resolved PostgreSQL connection.

Purpose
-------

The published ingestion metadata currently expects:

    source_db.public.employee

However, the dynamic connection resolved by ConnectionService
points to:

    demo_source_db.public.customer

Before changing any metadata, we inspect the actual CUSTOMER table
and its physical columns.

This script is READ-ONLY.

It does not:

    - modify metadata
    - modify source data
    - modify target data
    - create tables
    - delete tables
    - update mappings

Execution flow:

    ConnectionService
          |
          v
    ConnectionMetadata
          |
          v
    ConnectorFactory
          |
          v
    PostgreSQLConnector
          |
          v
    demo_source_db
          |
          v
    public.customer
          |
          v
    Column Discovery
"""


from __future__ import annotations

from app.connectors.factory import ConnectorFactory
from app.connectors.postgres.adapter import PostgreSQLConnector
from app.connectors.registry import ConnectorRegistry
from app.services.connection_service import ConnectionService


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
# These values identify the physical object discovered through the
# dynamic source connection.
#
# They are intentionally kept separate from the published employee
# metadata because this script is investigating the actual physical
# source database.
CONNECTION_ID = 1
SCHEMA_NAME = "public"
TABLE_NAME = "customer"


# ---------------------------------------------------------------------------
# CREATE CONNECTOR REGISTRY
# ---------------------------------------------------------------------------
def create_registry() -> ConnectorRegistry:
    """
    Create the connector registry used by this inspection script.

    WHY
    ---
    The registry maps the connector code stored in metadata to the
    actual Python connector implementation.

    For this POC:

        POSTGRESQL_CONNECTOR
                |
                v
        PostgreSQLConnector
    """

    # Create an empty connector registry.
    registry = ConnectorRegistry()

    # Register the PostgreSQL connector implementation.
    registry.register(
        "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
    )

    return registry


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Resolve the dynamic connection and inspect customer columns.

    This function is completely read-only.
    """

    print("=" * 80)
    print("INSPECT DYNAMIC CUSTOMER SOURCE")
    print("=" * 80)

    # The connector is created later. Keeping the variable initialized
    # to None allows the finally block to safely close it if required.
    connector = None

    try:
        # -------------------------------------------------------------------
        # STEP 1 - RESOLVE CONNECTION METADATA
        # -------------------------------------------------------------------
        # ConnectionService reads the dynamic connection configuration
        # from the metadata database.
        connection_service = ConnectionService()

        connection_metadata = (
            connection_service.get_connection_metadata(
                CONNECTION_ID
            )
        )

        print()
        print("DYNAMIC CONNECTION")
        print("-" * 80)

        print(
            f"Connection ID : "
            f"{connection_metadata.connection_id}"
        )

        print(
            f"Connection    : "
            f"{connection_metadata.connection_name}"
        )

        print(
            f"Connector     : "
            f"{connection_metadata.connector_code}"
        )

        print(
            f"Host          : "
            f"{connection_metadata.host_name}"
        )

        print(
            f"Port          : "
            f"{connection_metadata.port_no}"
        )

        print(
            f"Database      : "
            f"{connection_metadata.database_name}"
        )

        # -------------------------------------------------------------------
        # STEP 2 - CREATE CONNECTOR
        # -------------------------------------------------------------------
        # The factory creates the appropriate connector implementation
        # based on the connector code resolved from metadata.
        registry = create_registry()

        factory = ConnectorFactory(registry)

        connector = factory.create(
            connection_metadata
        )

        print()
        print(
            f"Connector Implementation : "
            f"{type(connector).__name__}"
        )

        # -------------------------------------------------------------------
        # STEP 3 - TEST CONNECTION
        # -------------------------------------------------------------------
        # Verify that the dynamically resolved connection can actually
        # connect to the physical PostgreSQL database.
        print()
        print("CONNECTION TEST")
        print("-" * 80)

        if not connector.test_connection():
            raise RuntimeError(
                "Dynamic source connection test failed."
            )

        print(
            "Connection successful."
        )

        # -------------------------------------------------------------------
        # STEP 4 - DISCOVER TABLE COLUMNS
        # -------------------------------------------------------------------
        # list_columns() performs metadata discovery against the physical
        # database.
        #
        # IMPORTANT:
        #
        # The current PostgreSQLConnector implementation returns each
        # column as a dictionary.
        #
        # Example:
        #
        # {
        #     "column_name": "customer_id",
        #     "data_type": "integer",
        #     ...
        # }
        #
        # Therefore the code below uses dictionary access:
        #
        #     column["column_name"]
        #
        # instead of:
        #
        #     column.column_name
        print()
        print(
            f"COLUMN DISCOVERY - "
            f"{SCHEMA_NAME}.{TABLE_NAME}"
        )
        print("-" * 80)

        columns = connector.list_columns(
            SCHEMA_NAME,
            TABLE_NAME,
        )

        if not columns:
            print(
                "No columns were discovered."
            )
            return

        # -------------------------------------------------------------------
        # STEP 5 - DISPLAY COLUMN METADATA
        # -------------------------------------------------------------------
        print()
        print(
            "COLUMN NAME"
            " | DATA TYPE"
            " | NULLABLE"
            " | ORDINAL"
        )
        print("-" * 80)

        # list_columns() returns dictionaries, so use dictionary keys.
        for column in columns:
            print(
                f"{column.get('column_name')}"
                f" | {column.get('data_type')}"
                f" | {column.get('is_nullable')}"
                f" | {column.get('ordinal_position')}"
            )

        # -------------------------------------------------------------------
        # STEP 6 - SUMMARY
        # -------------------------------------------------------------------
        print()
        print("=" * 80)
        print("CUSTOMER TABLE INSPECTION COMPLETE")
        print("=" * 80)

        print()
        print(
            f"Physical Source : "
            f"{connection_metadata.database_name}"
            f".{SCHEMA_NAME}"
            f".{TABLE_NAME}"
        )

        print(
            f"Column Count    : "
            f"{len(columns)}"
        )

        print()
        print(
            "No metadata or source data was modified."
        )

    finally:
        # -------------------------------------------------------------------
        # STEP 7 - CLEANUP
        # -------------------------------------------------------------------
        # Always close the connector so the database connection is
        # released even if an exception occurs.
        if connector is not None:
            connector.close()


# ---------------------------------------------------------------------------
# MODULE ENTRY POINT
# ---------------------------------------------------------------------------
# Allows this script to be executed using:
#
#     python -m scripts.inspect_dynamic_customer
#
if __name__ == "__main__":
    main()