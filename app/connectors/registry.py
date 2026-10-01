"""
Connector Registry
==================

The Connector Registry maintains the mapping between a metadata
connector code and its Python connector implementation.

Example:

    Metadata:
        POSTGRESQL_CONNECTOR

    Registry:
        POSTGRESQL_CONNECTOR -> PostgreSQLConnector


Why do we need a registry?
--------------------------

The ingestion engine should not contain code such as:

    if database == "postgres":
        use PostgreSQLConnector()

    elif database == "mysql":
        use MySQLConnector()

Instead, the metadata tells the platform which connector is
required and the registry resolves that connector dynamically.

Architecture:

    connection metadata
            |
            v
    connector_code
            |
            v
    ConnectorRegistry
            |
            v
    Connector implementation
"""


from typing import Type

from app.connectors.base import BaseConnector


class ConnectorRegistry:
    """
    Stores all registered database connector implementations.

    The registry is intentionally independent of any particular
    database technology.
    """

    def __init__(self) -> None:
        """
        Initialize an empty connector registry.

        The dictionary stores:

            connector_code -> connector class

        Example:

            {
                "POSTGRESQL_CONNECTOR":
                    PostgreSQLConnector
            }
        """

        self._connectors: dict[
            str,
            Type[BaseConnector],
        ] = {}

    # =========================================================
    # REGISTER CONNECTOR
    # =========================================================

    def register(
        self,
        connector_code: str,
        connector_class: Type[BaseConnector],
    ) -> None:
        """
        Register a connector implementation.

        Parameters
        ----------
        connector_code:
            The code stored in the metadata database.

        connector_class:
            Python class implementing BaseConnector.

        Example:

            registry.register(
                "POSTGRESQL_CONNECTOR",
                PostgreSQLConnector,
            )

        WHY:
        ----
        This allows new database connectors to be added without
        changing the core ingestion engine.
        """

        # -----------------------------------------------------
        # Normalize the connector code.
        #
        # This prevents differences such as:
        #
        #     postgres
        #     POSTGRES
        #     PostgreSQL
        #
        # from causing unnecessary lookup problems.
        # -----------------------------------------------------

        normalized_code = (
            connector_code
            .strip()
            .upper()
        )

        if not normalized_code:
            raise ValueError(
                "connector_code cannot be empty."
            )

        # -----------------------------------------------------
        # Validate that the implementation follows the common
        # BaseConnector contract.
        # -----------------------------------------------------

        if not issubclass(
            connector_class,
            BaseConnector,
        ):
            raise TypeError(
                f"{connector_class.__name__} must inherit "
                "from BaseConnector."
            )

        # -----------------------------------------------------
        # Prevent accidental duplicate registration.
        # -----------------------------------------------------

        if normalized_code in self._connectors:

            raise ValueError(
                f"Connector already registered: "
                f"{normalized_code}"
            )

        self._connectors[
            normalized_code
        ] = connector_class

    # =========================================================
    # GET CONNECTOR
    # =========================================================

    def get(
        self,
        connector_code: str,
    ) -> Type[BaseConnector]:
        """
        Retrieve a registered connector class.

        Parameters
        ----------
        connector_code:
            Connector code retrieved from metadata.

        Returns
        -------
        Type[BaseConnector]
            Registered connector implementation.

        Example:

            PostgreSQLConnector =
                registry.get(
                    "POSTGRESQL_CONNECTOR"
                )
        """

        normalized_code = (
            connector_code
            .strip()
            .upper()
        )

        if not normalized_code:
            raise ValueError(
                "connector_code cannot be empty."
            )

        try:

            return self._connectors[
                normalized_code
            ]

        except KeyError as exc:

            supported = (
                self.supported_connectors()
            )

            raise ValueError(
                f"No connector registered for "
                f"'{normalized_code}'. "
                f"Supported connectors: {supported}"
            ) from exc

    # =========================================================
    # LIST CONNECTORS
    # =========================================================

    def supported_connectors(self) -> list[str]:
        """
        Return all registered connector codes.

        WHY:
        ----
        This is useful for:

            - testing
            - API responses
            - UI dropdowns
            - health checks
            - connector administration
        """

        return sorted(
            self._connectors.keys()
        )

    # =========================================================
    # CHECK CONNECTOR
    # =========================================================

    def is_registered(
        self,
        connector_code: str,
    ) -> bool:
        """
        Check whether a connector has been registered.
        """

        normalized_code = (
            connector_code
            .strip()
            .upper()
        )

        return (
            normalized_code
            in self._connectors
        )