"""
Source Column Discovery Test
============================

Validates column metadata discovery for a source table.
"""

from app.connectors.factory import ConnectorFactory
from app.connectors.register_connectors import (
    create_connector_registry,
)
from app.services.connection_service import (
    ConnectionService,
)


def main() -> None:

    connection_id = 1

    schema_name = "public"
    table_name = "customer"

    # =========================================================
    # Resolve connection metadata
    # =========================================================

    connection_service = ConnectionService()

    metadata = (
        connection_service
        .get_connection_metadata(
            connection_id
        )
    )

    print("=" * 70)
    print("SOURCE COLUMN DISCOVERY")
    print("=" * 70)

    print(
        f"Connection : "
        f"{metadata.connection_name}"
    )

    print(
        f"Database   : "
        f"{metadata.database_name}"
    )

    print(
        f"Schema     : "
        f"{schema_name}"
    )

    print(
        f"Table      : "
        f"{table_name}"
    )

    # =========================================================
    # Create connector
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

    try:

        # =====================================================
        # Connect
        # =====================================================

        print(
            "\nConnecting to source database..."
        )

        connector.connect()

        print(
            "Source database connection successful!"
        )

        # =====================================================
        # Discover columns
        # =====================================================

        print(
            "\nDiscovering columns..."
        )

        columns = (
            connector.list_columns(
                schema_name,
                table_name,
            )
        )

        print(
            "\nSOURCE COLUMNS"
        )

        if not columns:

            print(
                "  No columns found."
            )

        else:

            for column in columns:

                print(
                    f"  {column['ordinal_position']}. "
                    f"{column['column_name']} | "
                    f"{column['data_type']} | "
                    f"Nullable: {column['is_nullable']}"
                )

        # =====================================================
        # Summary
        # =====================================================

        print(
            "\n" + "=" * 70
        )

        print(
            "COLUMN DISCOVERY COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 70
        )

    finally:

        connector.close()

        print(
            "\nSource database connection closed."
        )


if __name__ == "__main__":
    main()