"""
Connector Registration
======================

This module registers all certified database connectors that are
available to the Metadata-Driven Data Ingestion Platform.

WHY THIS FILE EXISTS
--------------------

The ingestion engine should NOT contain database-specific logic.

For example, we do NOT want:

    if connector == "POSTGRESQL":
        ...
    elif connector == "MYSQL":
        ...

Instead, connectors are registered centrally here.

The metadata database provides a connector code such as:

    POSTGRESQL_CONNECTOR

The registry maps that code to the corresponding Python
implementation:

    POSTGRESQL_CONNECTOR
            |
            v
    PostgreSQLConnector


FUTURE CONNECTORS
-----------------

Additional connectors can be registered here without changing
the ingestion engine.

Examples:

    MYSQL_CONNECTOR
    SQLSERVER_CONNECTOR
    ORACLE_CONNECTOR
    SNOWFLAKE_CONNECTOR
    DATABRICKS_CONNECTOR
"""

from app.connectors.registry import ConnectorRegistry
from app.connectors.postgres.adapter import PostgreSQLConnector


def create_connector_registry() -> ConnectorRegistry:
    """
    Create and configure the application connector registry.

    Returns
    -------
    ConnectorRegistry
        Registry containing all certified connectors available
        to the application.

    WHY
    ---
    The registry provides a central mapping between the connector
    code stored in metadata and the Python connector implementation.

    Currently supported:

        POSTGRESQL_CONNECTOR
            |
            v
        PostgreSQLConnector

    As new connectors are developed, they can be registered here.
    """

    # =========================================================
    # CREATE EMPTY REGISTRY
    # =========================================================
    #
    # The registry initially contains no connectors.
    # =========================================================

    registry = ConnectorRegistry()

    # =========================================================
    # REGISTER POSTGRESQL CONNECTOR
    # =========================================================
    #
    # The connector code MUST match the connector_code stored
    # in the metadata database.
    #
    # Example:
    #
    #     conn.connector.connector_code
    #
    # should contain:
    #
    #     POSTGRESQL_CONNECTOR
    #
    # The registry then resolves that code to:
    #
    #     PostgreSQLConnector
    # =========================================================

    registry.register(
        "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
    )

    # =========================================================
    # RETURN CONFIGURED REGISTRY
    # =========================================================
    #
    # The ConnectorFactory will use this registry to dynamically
    # create the appropriate connector.
    # =========================================================

    return registry