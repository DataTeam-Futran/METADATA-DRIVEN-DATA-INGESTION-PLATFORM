"""
Full Load Source Read Test
==========================

Validates the first full-load extraction step.

Flow:

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
    public.customer
          ↓
    read_batches()
          ↓
    Source Rows
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
    # STEP 1 - Source connection metadata
    # =========================================================

    connection_id = 1

    schema_name = "public"
    table_name = "customer"

    connection_service = ConnectionService()

    metadata = (
        connection_service
        .get_connection_metadata(
            connection_id
        )
    )

    print("=" * 70)
    print("FULL LOAD SOURCE READ")
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
        # STEP 4 - Build source query
        # =====================================================

        query = """
            SELECT *
            FROM "public"."customer"
            ORDER BY "customer_id";
        """

        print(
            "\nSource Query:"
        )

        print(
            query.strip()
        )

        # =====================================================
        # STEP 5 - Read source data in batches
        # =====================================================

        batch_size = 2

        print(
            f"\nReading source data "
            f"with batch size = {batch_size}..."
        )

        total_rows = 0
        batch_number = 0

        for batch in connector.read_batches(
            query=query,
            batch_size=batch_size,
        ):

            batch_number += 1

            batch_row_count = len(batch)

            total_rows += batch_row_count

            print(
                f"\nBatch {batch_number}"
            )

            print(
                f"Rows in batch : "
                f"{batch_row_count}"
            )

            for row in batch:

                print(
                    f"  {row}"
                )

        # =====================================================
        # STEP 6 - Summary
        # =====================================================

        print(
            "\n" + "=" * 70
        )

        print(
            "FULL LOAD SOURCE READ COMPLETED"
        )

        print(
            "=" * 70
        )

        print(
            f"Total batches : "
            f"{batch_number}"
        )

        print(
            f"Total rows    : "
            f"{total_rows}"
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