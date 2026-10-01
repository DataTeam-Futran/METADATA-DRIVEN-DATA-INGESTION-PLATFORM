"""
Customer Source-to-Metadata Reconciliation

Purpose:
    Reconcile the physical PostgreSQL source with the metadata registered
    in the catalog before implementing the ingestion runtime.

Validation performed:
    1. Resolve Connection ID 1 dynamically.
    2. Resolve Dataset ID 7 / Binding ID 7 from catalog metadata.
    3. Confirm the catalog binding points to Connection ID 1.
    4. Confirm database, schema, and object name.
    5. Discover the physical source columns through PostgreSQLConnector.
    6. Check whether a catalog schema version already exists.
    7. Compare physical columns with the published schema metadata when
       a schema version exists.

Important:
    This script is READ-ONLY.
    It does not modify catalog, connection, mapping, or ingestion metadata.
"""

from __future__ import annotations

# Import the metadata-store connection used for read-only catalog queries.
from app.db.metastore import get_metastore_connection

# Import the existing dynamic connection service.
from app.services.connection_service import ConnectionService

# Import the existing connector registry and factory.
from app.connectors.registry import ConnectorRegistry
from app.connectors.factory import ConnectorFactory

# Import the existing PostgreSQL connector implementation.
from app.connectors.postgres.adapter import PostgreSQLConnector


# These are the exact Customer POC metadata identifiers already registered.
DATASET_ID = 7
DATASET_BINDING_ID = 7
CONNECTION_ID = 1


def create_connector_factory() -> ConnectorFactory:
    """
    Create the existing connector factory.

    PostgreSQL is registered here because the current POC source uses
    the PostgreSQL connector.
    """

    # Create an empty connector registry.
    registry = ConnectorRegistry()

    # Register the existing PostgreSQL implementation.
    registry.register(
        "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
    )

    # Return the generic connector factory.
    return ConnectorFactory(registry)


def get_binding_metadata(connection) -> dict:
    """
    Read the Customer dataset binding from the catalog.

    This tells us which physical connection, database, schema, and object
    the catalog says should be used.
    """

    # Query the authoritative catalog binding.
    query = """
        SELECT
            dataset_binding_id,
            tenant_id,
            dataset_id,
            environment_id,
            connection_id,
            catalog_name,
            schema_name,
            object_name,
            object_name_normalized,
            status_code
        FROM catalog.dataset_binding
        WHERE dataset_binding_id = %s
          AND dataset_id = %s
        LIMIT 1;
    """

    # Execute the query inside the existing metadata-store connection.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                DATASET_BINDING_ID,
                DATASET_ID,
            ),
        )

        row = cursor.fetchone()

    # Stop if the expected binding does not exist.
    if row is None:
        raise LookupError(
            "Customer dataset binding was not found."
        )

    # Convert the database row into a readable dictionary.
    return {
        "dataset_binding_id": row[0],
        "tenant_id": row[1],
        "dataset_id": row[2],
        "environment_id": row[3],
        "connection_id": row[4],
        "catalog_name": row[5],
        "schema_name": row[6],
        "object_name": row[7],
        "object_name_normalized": row[8],
        "status_code": row[9],
    }


def get_current_schema_version(connection) -> dict | None:
    """
    Find the current catalog schema version for the Customer dataset.

    If no schema version exists, None is returned.

    This is important because the current POC has registered the dataset
    and binding, but the actual discovered schema has not yet been captured.
    """

    # Look for the current schema version.
    query = """
        SELECT
            schema_version_id,
            dataset_id,
            source_binding_id,
            version_no,
            schema_hash,
            source_code,
            change_type_code,
            is_current
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s
          AND is_current = true
        ORDER BY version_no DESC
        LIMIT 1;
    """

    # Execute the read-only metadata query.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (DATASET_ID,),
        )

        row = cursor.fetchone()

    # Return None when the schema has not yet been captured.
    if row is None:
        return None

    # Return the current schema metadata.
    return {
        "schema_version_id": row[0],
        "dataset_id": row[1],
        "source_binding_id": row[2],
        "version_no": row[3],
        "schema_hash": row[4],
        "source_code": row[5],
        "change_type_code": row[6],
        "is_current": row[7],
    }


def get_schema_fields(
    connection,
    schema_version_id: int,
) -> list[dict]:
    """
    Read the fields belonging to a catalog schema version.
    """

    # Retrieve fields in their published ordinal order.
    query = """
        SELECT
            field_id,
            ordinal_no,
            field_name,
            native_datatype_id,
            source_datatype_text,
            length_value,
            precision_value,
            scale_value,
            is_nullable
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    # Execute the field lookup.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (schema_version_id,),
        )

        rows = cursor.fetchall()

    # Convert database rows into dictionaries.
    return [
        {
            "field_id": row[0],
            "ordinal_no": row[1],
            "field_name": row[2],
            "native_datatype_id": row[3],
            "source_datatype_text": row[4],
            "length_value": row[5],
            "precision_value": row[6],
            "scale_value": row[7],
            "is_nullable": row[8],
        }
        for row in rows
    ]


def compare_physical_and_published(
    physical_columns: list[dict],
    published_fields: list[dict],
) -> list[str]:
    """
    Compare the physical source columns with published catalog fields.

    The comparison intentionally focuses on structural characteristics
    that matter for ingestion:
        - ordinal
        - column name
        - datatype
        - nullable status
    """

    # Create a list to collect reconciliation differences.
    differences: list[str] = []

    # Compare the number of columns first.
    if len(physical_columns) != len(published_fields):
        differences.append(
            "COLUMN_COUNT_MISMATCH: "
            f"physical={len(physical_columns)}, "
            f"published={len(published_fields)}"
        )

    # Compare fields that exist on both sides.
    comparison_count = min(
        len(physical_columns),
        len(published_fields),
    )

    for index in range(comparison_count):

        # Read the physical source column.
        physical = physical_columns[index]

        # Read the published metadata field.
        published = published_fields[index]

        # Extract the physical column name.
        physical_name = physical.get("column_name")

        # Extract the published column name.
        published_name = published.get("field_name")

        # Compare names case-insensitively.
        if physical_name.lower() != published_name.lower():
            differences.append(
                f"FIELD_NAME_MISMATCH at ordinal {index + 1}: "
                f"physical={physical_name}, "
                f"published={published_name}"
            )

        # Extract physical datatype.
        physical_type = physical.get("data_type")

        # Extract published datatype text.
        published_type = published.get("source_datatype_text")

        # Compare datatype text when both values are available.
        if physical_type and published_type:
            if physical_type.lower() != published_type.lower():
                differences.append(
                    f"DATATYPE_MISMATCH for {physical_name}: "
                    f"physical={physical_type}, "
                    f"published={published_type}"
                )

        # Extract nullable flags.
        physical_nullable = physical.get("is_nullable")
        published_nullable = published.get("is_nullable")

        # Compare nullable behavior.
        if physical_nullable != published_nullable:
            differences.append(
                f"NULLABILITY_MISMATCH for {physical_name}: "
                f"physical={physical_nullable}, "
                f"published={published_nullable}"
            )

    # Return all detected differences.
    return differences


def main() -> None:
    """
    Execute the complete read-only reconciliation.
    """

    # Print a clear heading for terminal execution.
    print("=" * 72)
    print("CUSTOMER SOURCE / PUBLISHED METADATA RECONCILIATION")
    print("=" * 72)

    # Resolve Connection ID 1 using the existing dynamic connection service.
    connection_service = ConnectionService()

    # This retrieves connection metadata from the authoritative conn.*
    # metadata rather than hardcoding source connection properties.
    connection_metadata = connection_service.get_connection_metadata(
        CONNECTION_ID
    )

    # Display non-secret connection information.
    print()
    print("DYNAMIC CONNECTION")
    print("-" * 72)
    print(f"Connection ID   : {connection_metadata.connection_id}")
    print(f"Connection Name : {connection_metadata.connection_name}")
    print(f"Connector       : {connection_metadata.connector_code}")
    print(f"Host            : {connection_metadata.host_name}")
    print(f"Port            : {connection_metadata.port_no}")
    print(f"Database        : {connection_metadata.database_name}")

    # Create the generic connector factory.
    factory = create_connector_factory()

    # Create the PostgreSQL connector using the resolved metadata.
    connector = factory.create(connection_metadata)

    # Open a read-only metadata-store connection.
    with get_metastore_connection() as metastore_connection:

        # Resolve the catalog binding.
        binding = get_binding_metadata(
            metastore_connection
        )

        print()
        print("CATALOG DATASET BINDING")
        print("-" * 72)
        print(f"Dataset ID       : {binding['dataset_id']}")
        print(f"Binding ID       : {binding['dataset_binding_id']}")
        print(f"Tenant ID        : {binding['tenant_id']}")
        print(f"Connection ID    : {binding['connection_id']}")
        print(f"Database/Catalog : {binding['catalog_name']}")
        print(f"Schema           : {binding['schema_name']}")
        print(f"Object           : {binding['object_name']}")
        print(f"Status            : {binding['status_code']}")

        # Verify that the binding points to the expected dynamic connection.
        if binding["connection_id"] != CONNECTION_ID:
            raise ValueError(
                "RECONCILIATION FAILED: "
                "Catalog binding does not point to Connection 1."
            )

        # Verify database metadata.
        if (
            binding["catalog_name"]
            != connection_metadata.database_name
        ):
            raise ValueError(
                "RECONCILIATION FAILED: "
                "Catalog database does not match Connection metadata."
            )

        # Connect to the physical PostgreSQL source.
        connector.connect()

        try:
            # Discover the actual physical source columns.
            physical_columns = connector.list_columns(
                schema_name=binding["schema_name"],
                table_name=binding["object_name"],
            )

            print()
            print("PHYSICAL SOURCE")
            print("-" * 72)
            print(
                f"{'Ordinal':<10}"
                f"{'Column':<25}"
                f"{'Datatype':<25}"
                f"{'Nullable':<10}"
            )

            # Display every discovered source column.
            for column in physical_columns:
                print(
                    f"{str(column.get('ordinal_position')):<10}"
                    f"{str(column.get('column_name')):<25}"
                    f"{str(column.get('data_type')):<25}"
                    f"{str(column.get('is_nullable')):<10}"
                )

        finally:
            # Always close the physical source connection.
            connector.close()

        # Read the current published schema version, if one exists.
        schema_version = get_current_schema_version(
            metastore_connection
        )

        print()
        print("PUBLISHED SCHEMA")
        print("-" * 72)

        # No schema version means dataset/binding registration exists,
        # but actual source schema capture has not happened yet.
        if schema_version is None:
            print("No published schema version exists yet.")
            print(
                "STATUS: DATASET/BINDING REGISTERED - "
                "SCHEMA CAPTURE REQUIRED"
            )

        else:
            # Display the existing published schema information.
            print(
                f"Schema Version ID : "
                f"{schema_version['schema_version_id']}"
            )
            print(
                f"Version Number    : "
                f"{schema_version['version_no']}"
            )
            print(
                f"Schema Hash       : "
                f"{schema_version['schema_hash']}"
            )

            # Retrieve the published schema fields.
            published_fields = get_schema_fields(
                metastore_connection,
                schema_version["schema_version_id"],
            )

            # Compare physical and published schemas.
            differences = compare_physical_and_published(
                physical_columns,
                published_fields,
            )

            # Report reconciliation result.
            if differences:
                print()
                print("RECONCILIATION RESULT: MISMATCH")
                print("-" * 72)

                # Print every structural difference.
                for difference in differences:
                    print(f"- {difference}")

            else:
                print()
                print("RECONCILIATION RESULT: MATCH")
                print(
                    "Physical source and published schema are aligned."
                )

    # Print the final result for the current state.
    print()
    print("=" * 72)
    print("RECONCILIATION COMPLETE")
    print("=" * 72)
    print(
        "No metadata was modified by this script."
    )


# Execute the script when run with python -m.
if __name__ == "__main__":
    main()