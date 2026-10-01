"""
Source Table Discovery Test
===========================

Validates:

    Connection ID
        ↓
    ConnectionService
        ↓
    ConnectionMetadata
        ↓
    ConnectorFactory
        ↓
    PostgreSQLConnector
        ↓
    CredentialResolver
        ↓
    Source PostgreSQL
        ↓
    public schema
        ↓
    Table Discovery
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
    # STEP 1 - Resolve connection metadata
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
    print("SOURCE TABLE DISCOVERY")
    print("=" * 70)

    print(
        f"Connection ID   : "
        f"{metadata.connection_id}"
    )

    print(
        f"Connection Name : "
        f"{metadata.connection_name}"
    )

    print(
        f"Database        : "
        f"{metadata.database_name}"
    )

    print(
        f"Credential ID   : "
        f"{metadata.credential_id}"
    )

    # =========================================================
    # STEP 2 - Create connector
    # =========================================================

    registry = (
        create_connector_registry()
    )

    factory = ConnectorFactory(
        registry
    )

    connector = factory.create(
        metadata
    )

    print(
        f"\nSelected Connector: "
        f"{connector.__class__.__name__}"
    )

    try:

        # =====================================================
        # STEP 3 - Connect to source
        # =====================================================

        print(
            "\nConnecting to source database..."
        )

        connector.connect()

        print(
            "Source database connection successful!"
        )

        # =====================================================
        # STEP 4 - Discover schemas
        # =====================================================

        print(
            "\nDiscovering schemas..."
        )

        schemas = (
            connector.list_schemas()
        )

        print(
            "\nSOURCE SCHEMAS"
        )

        for schema in schemas:

            print(
                f"  {schema}"
            )

        # =====================================================
        # STEP 5 - Discover tables
        # =====================================================

        print(
            "\nDiscovering tables..."
        )

        for schema in schemas:

            print(
                f"\nSCHEMA: {schema}"
            )

            tables = (
                connector.list_tables(
                    schema
                )
            )

            if not tables:

                print(
                    "  No tables found."
                )

                continue

            for table in tables:

                print(
                    f"  {table}"
                )

        # =====================================================
        # STEP 6 - Summary
        # =====================================================

        print(
            "\n" + "=" * 70
        )

        print(
            "TABLE DISCOVERY COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 70
        )

    finally:

        # =====================================================
        # STEP 7 - Close connection
        # =====================================================

        connector.close()

        print(
            "\nSource database connection closed."
        )


if __name__ == "__main__":
    main()