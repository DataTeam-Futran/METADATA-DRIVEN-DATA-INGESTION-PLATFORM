"""
Customer Runtime Connection Resolution Test

Purpose
-------
Validates that runtime connection IDs can dynamically resolve to the
appropriate connector implementation.

Current Customer POC:

    Source connection ID 1
        -> Demo PostgreSQL Connection
        -> POSTGRESQL_CONNECTOR

    Target connection ID 11
        -> Demo PostgreSQL Target Connection
        -> POSTGRESQL_CONNECTOR

This test does NOT open a physical database connection.

It only validates:

    connection_id
        -> ConnectionMetadata
        -> ConnectorFactory
        -> PostgreSQLConnector

The test is therefore read-only with respect to the metadata database.
"""

from app.connectors.postgres.adapter import PostgreSQLConnector
from app.runtime.connection_resolver import RuntimeConnectionResolver


def main() -> None:
    """
    Execute the Customer runtime connection resolution test.
    """

    # These are the connection IDs already created and validated in the
    # metadata store.
    source_connection_id = 1
    target_connection_id = 11

    # Create the runtime resolver.
    #
    # The resolver internally uses:
    #
    #     ConnectionService
    #     ConnectorRegistry
    #     ConnectorFactory
    #
    # No database-specific logic is required here.
    resolver = RuntimeConnectionResolver()

    print("=" * 100)
    print("CUSTOMER RUNTIME CONNECTION RESOLUTION")
    print("=" * 100)

    # Resolve the source connection.
    #
    # This should return a PostgreSQLConnector because the metadata for
    # connection ID 1 contains POSTGRESQL_CONNECTOR.
    source_connector = resolver.resolve(
        source_connection_id
    )

    print()
    print("SOURCE CONNECTION")
    print("-" * 100)
    print(
        f"Connector Class         : "
        f"{source_connector.__class__.__name__}"
    )
    print(
        f"Connection ID           : "
        f"{source_connector.metadata.connection_id}"
    )
    print(
        f"Connection Name         : "
        f"{source_connector.metadata.connection_name}"
    )
    print(
        f"Connector Code          : "
        f"{source_connector.metadata.connector_code}"
    )
    print(
        f"Database                 : "
        f"{source_connector.metadata.database_name}"
    )

    # Resolve the target connection.
    #
    # Connection ID 11 is also PostgreSQL in the current POC, but it is
    # deliberately resolved independently from the source.
    target_connector = resolver.resolve(
        target_connection_id
    )

    print()
    print("TARGET CONNECTION")
    print("-" * 100)
    print(
        f"Connector Class         : "
        f"{target_connector.__class__.__name__}"
    )
    print(
        f"Connection ID           : "
        f"{target_connector.metadata.connection_id}"
    )
    print(
        f"Connection Name         : "
        f"{target_connector.metadata.connection_name}"
    )
    print(
        f"Connector Code          : "
        f"{target_connector.metadata.connector_code}"
    )
    print(
        f"Database                 : "
        f"{target_connector.metadata.database_name}"
    )

    # Validate that the source connector is the expected PostgreSQL
    # implementation.
    assert isinstance(
        source_connector,
        PostgreSQLConnector,
    )

    # Validate the source connection metadata.
    assert (
        source_connector.metadata.connection_id
        == source_connection_id
    )

    assert (
        source_connector.metadata.connector_code
        == "POSTGRESQL_CONNECTOR"
    )

    assert (
        source_connector.metadata.database_name
        == "demo_source_db"
    )

    # Validate that the target connector is also the expected PostgreSQL
    # implementation for the current POC.
    assert isinstance(
        target_connector,
        PostgreSQLConnector,
    )

    # Validate the target connection metadata.
    assert (
        target_connector.metadata.connection_id
        == target_connection_id
    )

    assert (
        target_connector.metadata.connector_code
        == "POSTGRESQL_CONNECTOR"
    )

    assert (
        target_connector.metadata.database_name
        == "ingestion_metastore"
    )

    print()
    print("=" * 100)
    print("RUNTIME CONNECTION RESOLUTION PASSED")
    print("=" * 100)
    print("Source connection ID   : 1")
    print("Source connector       : PostgreSQLConnector")
    print("Source database        : demo_source_db")
    print()
    print("Target connection ID   : 11")
    print("Target connector       : PostgreSQLConnector")
    print("Target database        : ingestion_metastore")
    print()
    print("Physical connection    : NOT OPENED")
    print("Metadata modified      : NO")
    print("Operation              : READ ONLY")
    print("=" * 100)


if __name__ == "__main__":
    # Execute the test when this module is run directly.
    main()