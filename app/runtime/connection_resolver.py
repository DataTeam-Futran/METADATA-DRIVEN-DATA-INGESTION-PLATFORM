"""
Runtime Connection Resolver

Purpose
-------
This module converts a metadata connection_id into the correct connector
instance that can be used by the runtime execution engine.

Runtime flow:

    connection_id
          |
          v
    ConnectionService
          |
          v
    ConnectionMetadata
          |
          v
    ConnectorFactory
          |
          v
    BaseConnector implementation

For the current Customer POC:

    connection_id = 1
        -> Demo PostgreSQL Connection
        -> PostgreSQLConnector

    connection_id = 11
        -> Demo PostgreSQL Target Connection
        -> PostgreSQLConnector

Important
---------
This module does not hardcode PostgreSQL.

The connector type is determined from metadata using the connector_code
stored in the metadata database.
"""

from app.connectors.base import BaseConnector
from app.connectors.factory import ConnectorFactory
from app.connectors.register_connectors import create_connector_registry
from app.services.connection_service import ConnectionService


class RuntimeConnectionResolver:
    """
    Resolves a metadata connection ID into a connector instance.

    The resolver acts as the bridge between metadata and the connector
    execution layer.

    This keeps the runtime execution engine independent of specific
    database vendors.
    """

    def __init__(
        self,
        connection_service: ConnectionService | None = None,
        connector_factory: ConnectorFactory | None = None,
    ) -> None:
        """
        Initialize the runtime connection resolver.

        Parameters
        ----------
        connection_service:
            Service responsible for reading connection metadata.

        connector_factory:
            Factory responsible for creating the correct connector
            implementation from ConnectionMetadata.

        Dependency injection is used here so that the component can later
        be unit-tested with mock services and factories.
        """

        # Use the existing ConnectionService when one is not explicitly
        # supplied by the caller.
        self._connection_service = (
            connection_service
            if connection_service is not None
            else ConnectionService()
        )

        # Create the standard connector registry and factory when the caller
        # does not provide one.
        #
        # create_connector_registry() currently registers:
        #
        #     POSTGRESQL_CONNECTOR -> PostgreSQLConnector
        #
        # Additional connectors can be registered later without changing
        # this runtime resolver.
        self._connector_factory = (
            connector_factory
            if connector_factory is not None
            else ConnectorFactory(create_connector_registry())
        )

    def resolve(self, connection_id: int) -> BaseConnector:
        """
        Resolve a connection ID into a connector instance.

        Parameters
        ----------
        connection_id:
            Metadata connection identifier.

        Returns
        -------
        BaseConnector
            Connector implementation created from the connection metadata.

        Raises
        ------
        ValueError
            If the connection ID is invalid.

        LookupError
            If the connection metadata does not exist.

        Notes
        -----
        The connector is created but not connected to the physical database.

        Connection establishment is intentionally separated from connector
        creation so the execution engine can control when the physical
        connection is opened and closed.
        """

        # Validate the connection ID before accessing metadata.
        if connection_id <= 0:
            raise ValueError(
                "connection_id must be greater than zero."
            )

        # Read the connection metadata from the metadata store.
        #
        # ConnectionService already contains the metadata lookup logic, so
        # we reuse it instead of duplicating SQL in the runtime layer.
        metadata = self._connection_service.get_connection_metadata(
            connection_id
        )

        # Convert the metadata definition into the appropriate connector.
        #
        # The factory uses metadata.connector_code to select the correct
        # implementation from the connector registry.
        connector = self._connector_factory.create(metadata)

        # Return the connector without opening a physical database
        # connection yet.
        return connector