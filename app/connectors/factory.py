"""
Connector Factory
=================

The ConnectorFactory creates the correct database connector
dynamically based on connection metadata.

The ingestion engine should NOT contain database-specific
selection logic.

For example, the engine should not do this:

    if database == "postgres":
        PostgreSQLConnector()

    elif database == "mysql":
        MySQLConnector()

Instead:

    connection metadata
            |
            v
    connector_code
            |
            v
    ConnectorFactory
            |
            v
    ConnectorRegistry
            |
            v
    Database Connector
"""


from app.connectors.base import BaseConnector
from app.connectors.registry import ConnectorRegistry
from app.models.connection import ConnectionMetadata


class ConnectorFactory:
    """
    Factory responsible for creating database connectors.

    The factory does not know the implementation details of
    PostgreSQL, MySQL, SQL Server, Oracle, Snowflake, etc.

    It only asks the registry for the appropriate connector
    implementation.
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
    ) -> None:
        """
        Initialize the connector factory.

        Parameters
        ----------
        registry:
            Registry containing the available database
            connector implementations.
        """

        self.registry = registry

    def create(
        self,
        metadata: ConnectionMetadata,
    ) -> BaseConnector:
        """
        Create the appropriate connector dynamically.

        Parameters
        ----------
        metadata:
            Resolved connection metadata from the metadata
            database.

        Returns
        -------
        BaseConnector
            Concrete connector instance.

        Example
        -------
        If metadata contains:

            connector_code = POSTGRESQL_CONNECTOR

        the registry resolves:

            PostgreSQLConnector

        and this method returns:

            PostgreSQLConnector(metadata)
        """

        # -----------------------------------------------------
        # Get the connector class from the registry.
        #
        # The registry uses connector_code from metadata to
        # identify the correct implementation.
        # -----------------------------------------------------

        connector_class = self.registry.get(
            metadata.connector_code
        )

        # -----------------------------------------------------
        # Create an instance of the selected connector.
        #
        # Connection metadata is passed into the connector so
        # that host, port, database, parameters, etc. remain
        # dynamically resolved.
        # -----------------------------------------------------

        connector = connector_class(
            metadata
        )

        return connector