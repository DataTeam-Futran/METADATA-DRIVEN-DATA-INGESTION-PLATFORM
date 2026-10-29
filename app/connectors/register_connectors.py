
"""
Connector Registration
======================

Purpose
-------
Register supported database connector implementations centrally.

Why
---
The ConnectorFactory uses connector codes from metadata to select
the correct connector without hardcoding vendor logic in the executor.

Current registrations:
    POSTGRESQL_CONNECTOR -> PostgreSQLConnector
    SQLSERVER_CONNECTOR  -> SQLServerConnector
"""

# Import the central registry used to store connector implementations.
from app.connectors.registry import ConnectorRegistry

# Import the existing PostgreSQL connector.
from app.connectors.postgres.adapter import PostgreSQLConnector

# Import the new SQL Server connector.
from app.connectors.sqlserver.adapter import SQLServerConnector


def create_connector_registry() -> ConnectorRegistry:
    """
    Create and return the registry containing supported connectors.

    Returns
    -------
    ConnectorRegistry
        Registry mapping metadata connector codes to Python classes.
    """

    # Create an empty registry before registering implementations.
    registry = ConnectorRegistry()

    # Preserve the existing PostgreSQL connector registration.
    registry.register(
    "POSTGRESQL",
       PostgreSQLConnector,
   )

    registry.register(
       "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
   )

    # Register SQL Server using the exact connector code stored in metadata.
    registry.register(
        "SQL_SERVER_CONNECTOR",
        SQLServerConnector,
    )

    # Return the configured registry for use by ConnectorFactory.
    return registry
