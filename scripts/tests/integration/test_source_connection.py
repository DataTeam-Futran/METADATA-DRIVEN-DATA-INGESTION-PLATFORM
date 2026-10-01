"""
Dynamic Source Connection Test
==============================

This script validates the complete source connection framework.

Flow:

    Metadata PostgreSQL
            ↓
    ConnectionService
            ↓
    ConnectionMetadata
            ↓
    ConnectorRegistry
            ↓
    ConnectorFactory
            ↓
    PostgreSQLConnector
            ↓
    CredentialResolver
            ↓
    SecretProvider
            ↓
    Source PostgreSQL Database
            ↓
    Schema Discovery
"""

from app.connectors.factory import ConnectorFactory
from app.connectors.register_connectors import (
    create_connector_registry,
)
from app.services.connection_service import (
    ConnectionService,
)


def main() -> None:

    # =========================================================
    # STEP 1
    # =========================================================
    # The application receives only a connection_id.
    #
    # Host, port, database, username and connector information
    # are resolved dynamically from the metadata database.
    #
    # credential_id is also resolved from the metadata and is
    # used later by CredentialResolver.
    # =========================================================

    connection_id = 1

    connection_service = ConnectionService()

    metadata = (
        connection_service
        .get_connection_metadata(
            connection_id
        )
    )

    print("=" * 70)
    print("RESOLVED CONNECTION METADATA")
    print("=" * 70)

    print(
        f"Connection ID    : "
        f"{metadata.connection_id}"
    )

    print(
        f"Connection Name  : "
        f"{metadata.connection_name}"
    )

    print(
        f"Connector         : "
        f"{metadata.connector_code}"
    )

    print(
        f"Connector Version : "
        f"{metadata.connector_version}"
    )

    print(
        f"Host              : "
        f"{metadata.host_name}"
    )

    print(
        f"Port              : "
        f"{metadata.port_no}"
    )

    print(
        f"Database          : "
        f"{metadata.database_name}"
    )

    print(
        f"Role              : "
        f"{metadata.connection_role_code}"
    )

    print(
        f"Credential ID     : "
        f"{metadata.credential_id}"
    )

    print("\nDynamic Parameters:")

    for name, parameter in (
        metadata.parameters.items()
    ):

        if parameter.is_secret_ref:

            value = "***SECRET***"

        else:

            value = parameter.value

        print(
            f"  {name} = {value}"
        )

    # =========================================================
    # STEP 2
    # =========================================================
    # Create the connector registry.
    #
    # The registry contains the connectors supported by the
    # ingestion platform.
    # =========================================================

    registry = (
        create_connector_registry()
    )

    print(
        "\nSupported Connectors:"
    )

    print(
        registry.supported_connectors()
    )

    # =========================================================
    # STEP 3
    # =========================================================
    # Factory dynamically selects the appropriate connector
    # based on metadata.connector_code.
    # =========================================================

    factory = ConnectorFactory(
        registry
    )

    connector = factory.create(
        metadata
    )

    print(
        "\nSelected Connector:"
    )

    print(
        connector.__class__.__name__
    )

    # =========================================================
    # STEP 4
    # =========================================================
    # Test source database connectivity.
    #
    # Internally the PostgreSQL connector performs:
    #
    #     credential_id
    #           ↓
    #     CredentialResolver
    #           ↓
    #     conn.credential_ref
    #           ↓
    #     SecretProvider
    #           ↓
    #     runtime password
    #           ↓
    #     psycopg.connect()
    #
    # The actual password is never printed.
    # =========================================================

    print(
        "\nTesting source database connection..."
    )

    connected = (
        connector.test_connection()
    )

    if not connected:

        print(
            "Source database connection failed."
        )

        print(
            "Stopping source discovery because "
            "the connector is not connected."
        )

        connector.close()

        return

    print(
        "Source database connection successful!"
    )

    # =========================================================
    # STEP 5
    # =========================================================
    # Discover source schemas.
    #
    # This is the beginning of the metadata discovery layer.
    #
    # Because test_connection() succeeded, the connector has
    # an active PostgreSQL connection.
    # =========================================================

    print(
        "\nDiscovering source schemas..."
    )

    schemas = (
        connector.list_schemas()
    )

    print(
        "\nSOURCE SCHEMAS"
    )

    if not schemas:

        print(
            "  No user-accessible schemas found."
        )

    else:

        for schema in schemas:

            print(
                f"  {schema}"
            )

    # =========================================================
    # STEP 6
    # =========================================================
    # Close source connection.
    # =========================================================

    connector.close()

    print(
        "\nSource database connection closed."
    )

    print(
        "\nSource connection test completed successfully."
    )


if __name__ == "__main__":
    main()