
"""
Generic Metadata-Driven Source Schema Capture

Purpose:
    Discover a source table's physical schema and register it in:
      - catalog.schema_capture_run
      - catalog.dataset_schema_version
      - catalog.dataset_field

Usage:
    python -m scripts.metadata.capture_dataset_schema --dataset-id 10 --binding-id 10

Important:
    The dataset ID and binding ID must identify an existing ACTIVE source
    dataset and its ACTIVE binding. Verify the binding ID in your metastore
    before running the script.
"""

import argparse
import hashlib
import json
from typing import Any

import psycopg

from app.db.metastore import get_metastore_connection
from app.connectors.registry import ConnectorRegistry
from app.connectors.factory import ConnectorFactory
from app.connectors.postgres.adapter import PostgreSQLConnector
from app.services.connection_service import ConnectionService


REQUIRED_CAPABILITY_CODE = "SCHEMA_DISCOVERY"
CAPTURE_MODE_CODE = "DISCOVERY"
CAPTURE_STATUS_RUNNING = "RUNNING"
CAPTURE_STATUS_COMPLETED = "COMPLETED"
CAPTURE_STATUS_FAILED = "FAILED"


def print_section(title: str) -> None:
    """Print a readable section heading."""
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def create_connector_factory() -> ConnectorFactory:
    """
    Register connector implementations.

    PostgreSQL is registered here because this script currently uses the
    PostgreSQL connector implementation. Other connector types must be
    registered before this script can discover their schemas.
    """
    registry = ConnectorRegistry()
    registry.register("POSTGRESQL_CONNECTOR", PostgreSQLConnector)
    return ConnectorFactory(registry)


def get_dataset_catalog_context(
    cursor: psycopg.Cursor,
    dataset_id: int,
    binding_id: int,
) -> dict[str, Any]:
    """Validate the dataset and binding and return their metadata."""

    cursor.execute(
        """
        SELECT
            dataset_id,
            tenant_id,
            project_id,
            dataset_code,
            dataset_name,
            object_type_code,
            dataset_role_code,
            layer_code,
            status_code
        FROM catalog.dataset
        WHERE dataset_id = %s;
        """,
        (dataset_id,),
    )

    dataset = cursor.fetchone()

    if dataset is None:
        raise RuntimeError(
            f"Catalog dataset {dataset_id} was not found."
        )

    (
        resolved_dataset_id,
        tenant_id,
        project_id,
        dataset_code,
        dataset_name,
        object_type_code,
        dataset_role_code,
        layer_code,
        dataset_status,
    ) = dataset

    if dataset_status != "ACTIVE":
        raise RuntimeError(
            f"Dataset {resolved_dataset_id} is not ACTIVE."
        )

    cursor.execute(
        """
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
          AND dataset_id = %s;
        """,
        (binding_id, resolved_dataset_id),
    )

    binding = cursor.fetchone()

    if binding is None:
        raise RuntimeError(
            f"Binding {binding_id} was not found for dataset "
            f"{resolved_dataset_id}."
        )

    (
        resolved_binding_id,
        binding_tenant_id,
        binding_dataset_id,
        environment_id,
        connection_id,
        catalog_name,
        schema_name,
        object_name,
        object_name_normalized,
        binding_status,
    ) = binding

    if binding_status != "ACTIVE":
        raise RuntimeError(
            f"Binding {resolved_binding_id} is not ACTIVE."
        )

    if binding_tenant_id != tenant_id:
        raise RuntimeError(
            "Dataset and binding tenant IDs do not match."
        )

    if binding_dataset_id != resolved_dataset_id:
        raise RuntimeError(
            "The binding does not belong to the requested dataset."
        )

    if not schema_name or not object_name:
        raise RuntimeError(
            "The binding must define a schema name and object name."
        )

    return {
        "dataset_id": resolved_dataset_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "dataset_code": dataset_code,
        "dataset_name": dataset_name,
        "object_type_code": object_type_code,
        "dataset_role_code": dataset_role_code,
        "layer_code": layer_code,
        "dataset_binding_id": resolved_binding_id,
        "environment_id": environment_id,
        "connection_id": connection_id,
        "catalog_name": catalog_name,
        "schema_name": schema_name,
        "object_name": object_name,
        "object_name_normalized": object_name_normalized,
    }


def validate_schema_discovery_capability(
    cursor: psycopg.Cursor,
    connector_version_id: int,
) -> None:
    """Confirm that the configured connector supports schema discovery."""

    cursor.execute(
        """
        SELECT
            capability.capability_code,
            version_capability.is_supported
        FROM conn.connector_version_capability AS version_capability
        INNER JOIN conn.connector_capability AS capability
            ON capability.capability_id =
               version_capability.capability_id
        WHERE version_capability.connector_version_id = %s
          AND capability.capability_code = %s;
        """,
        (connector_version_id, REQUIRED_CAPABILITY_CODE),
    )

    record = cursor.fetchone()

    if record is None:
        raise RuntimeError(
            f"Capability {REQUIRED_CAPABILITY_CODE} is not configured "
            f"for connector version {connector_version_id}."
        )

    capability_code, is_supported = record

    if is_supported is not True:
        raise RuntimeError(
            f"Capability {capability_code} is not supported by "
            f"connector version {connector_version_id}."
        )

    print(f"Validated capability: {capability_code}")


def resolve_platform_id(
    cursor: psycopg.Cursor,
    connector_id: int,
) -> int:
    """Resolve the database platform from connector metadata."""

    cursor.execute(
        """
        SELECT platform_id
        FROM conn.connector
        WHERE connector_id = %s;
        """,
        (connector_id,),
    )

    record = cursor.fetchone()

    if record is None:
        raise RuntimeError(
            f"Connector {connector_id} was not found."
        )

    return int(record[0])


def resolve_native_datatype_id(
    cursor: psycopg.Cursor,
    platform_id: int,
    native_type_name: str,
) -> int:
    """Resolve a discovered physical datatype to its catalog ID."""

    normalized_type = native_type_name.strip().upper()

    cursor.execute(
        """
        SELECT native_datatype_id
        FROM dtype.native_datatype
        WHERE platform_id = %s
          AND status_code = 'ACTIVE'
          AND UPPER(native_type_name) = %s
        ORDER BY database_version_id;
        """,
        (platform_id, normalized_type),
    )

    records = cursor.fetchall()

    if not records:
        raise RuntimeError(
            f"No active datatype metadata found for platform "
            f"{platform_id} and type '{native_type_name}'."
        )

    if len(records) > 1:
        raise RuntimeError(
            f"Multiple active datatype definitions found for "
            f"platform {platform_id} and type '{native_type_name}'. "
            "Database-version-aware datatype resolution is required."
        )

    return int(records[0][0])


def discover_source_columns(
    connection_metadata: Any,
    schema_name: str,
    object_name: str,
) -> list[dict[str, Any]]:
    """Discover columns using the registered source connector."""

    factory = create_connector_factory()
    connector = factory.create(connection_metadata)

    try:
        connector.connect()
        columns = connector.list_columns(schema_name, object_name)

        if not columns:
            raise RuntimeError(
                f"No columns discovered for {schema_name}.{object_name}."
            )

        return columns
    finally:
        connector.close()


def normalize_columns(
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize column metadata returned by the connector."""

    normalized: list[dict[str, Any]] = []

    for column in columns:
        column_name = str(column["column_name"]).strip()
        data_type = str(column["data_type"]).strip()
        nullable_value = column["is_nullable"]

        if isinstance(nullable_value, bool):
            is_nullable = nullable_value
        else:
            is_nullable = str(nullable_value).strip().upper() == "YES"

        ordinal_position = int(column["ordinal_position"])
        default_expression = column.get("column_default")

        if not column_name:
            raise RuntimeError(
                "Schema discovery returned a column without a name."
            )

        if not data_type:
            raise RuntimeError(
                f"Column '{column_name}' has no datatype."
            )

        normalized.append(
            {
                "ordinal_position": ordinal_position,
                "field_name": column_name,
                "field_name_normalized": column_name.lower(),
                "source_datatype_text": data_type,
                "is_nullable": is_nullable,
                "default_expression": default_expression,
            }
        )

    normalized.sort(key=lambda item: item["ordinal_position"])
    return normalized


def calculate_schema_hash(
    columns: list[dict[str, Any]],
) -> str:
    """Calculate a deterministic hash of the discovered schema."""

    canonical_json = json.dumps(
        columns,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def create_capture_run(
    cursor: psycopg.Cursor,
    tenant_id: int,
    binding_id: int,
    connector_version_id: int,
) -> int:
    """Create a RUNNING schema capture record."""

    cursor.execute(
        """
        INSERT INTO catalog.schema_capture_run (
            tenant_id,
            dataset_binding_id,
            connector_version_id,
            capture_mode_code,
            status_code
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING schema_capture_run_id;
        """,
        (
            tenant_id,
            binding_id,
            connector_version_id,
            CAPTURE_MODE_CODE,
            CAPTURE_STATUS_RUNNING,
        ),
    )

    record = cursor.fetchone()

    if record is None:
        raise RuntimeError(
            "The database did not return schema_capture_run_id."
        )

    return int(record[0])


def find_existing_schema_version(
    cursor: psycopg.Cursor,
    dataset_id: int,
    schema_hash: str,
) -> int | None:
    """Find an existing schema version with the same hash."""

    cursor.execute(
        """
        SELECT schema_version_id
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s
          AND schema_hash = %s
        LIMIT 1;
        """,
        (dataset_id, schema_hash),
    )

    record = cursor.fetchone()
    return int(record[0]) if record else None


def get_next_schema_version_number(
    cursor: psycopg.Cursor,
    dataset_id: int,
) -> int:
    """Calculate the next version number for the dataset."""

    cursor.execute(
        """
        SELECT COALESCE(MAX(version_no), 0)
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s;
        """,
        (dataset_id,),
    )

    record = cursor.fetchone()
    return int(record[0]) + 1


def create_schema_version(
    cursor: psycopg.Cursor,
    tenant_id: int,
    dataset_id: int,
    binding_id: int,
    capture_run_id: int,
    version_number: int,
    schema_hash: str,
    source_code: str,
) -> int:
    """Create a new current schema version."""

    cursor.execute(
        """
        UPDATE catalog.dataset_schema_version
        SET is_current = FALSE,
            updated_at = NOW()
        WHERE dataset_id = %s
          AND is_current = TRUE;
        """,
        (dataset_id,),
    )

    change_type = "CREATE" if version_number == 1 else "ALTER"

    cursor.execute(
        """
        INSERT INTO catalog.dataset_schema_version (
            tenant_id,
            dataset_id,
            source_binding_id,
            schema_capture_run_id,
            version_no,
            schema_hash,
            source_code,
            change_type_code,
            is_current
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
        RETURNING schema_version_id;
        """,
        (
            tenant_id,
            dataset_id,
            binding_id,
            capture_run_id,
            version_number,
            schema_hash,
            source_code,
            change_type,
        ),
    )

    record = cursor.fetchone()

    if record is None:
        raise RuntimeError(
            "The database did not return schema_version_id."
        )

    return int(record[0])


def create_dataset_fields(
    cursor: psycopg.Cursor,
    tenant_id: int,
    schema_version_id: int,
    platform_id: int,
    columns: list[dict[str, Any]],
) -> None:
    """Insert discovered column definitions into the catalog."""

    for column in columns:
        native_datatype_id = resolve_native_datatype_id(
            cursor,
            platform_id,
            column["source_datatype_text"],
        )

        cursor.execute(
            """
            INSERT INTO catalog.dataset_field (
                tenant_id,
                schema_version_id,
                ordinal_no,
                field_name,
                field_name_normalized,
                native_datatype_id,
                source_datatype_text,
                length_value,
                precision_value,
                scale_value,
                is_nullable,
                default_expression,
                is_identity,
                is_generated
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                NULL, NULL, NULL, %s, %s, FALSE, FALSE
            );
            """,
            (
                tenant_id,
                schema_version_id,
                column["ordinal_position"],
                column["field_name"],
                column["field_name_normalized"],
                native_datatype_id,
                column["source_datatype_text"],
                column["is_nullable"],
                column["default_expression"],
            ),
        )


def complete_capture_run(
    cursor: psycopg.Cursor,
    capture_run_id: int,
) -> None:
    """Mark a capture run as COMPLETED."""

    cursor.execute(
        """
        UPDATE catalog.schema_capture_run
        SET status_code = %s,
            ended_at = NOW(),
            updated_at = NOW()
        WHERE schema_capture_run_id = %s;
        """,
        (CAPTURE_STATUS_COMPLETED, capture_run_id),
    )


def fail_capture_run(
    cursor: psycopg.Cursor,
    capture_run_id: int,
) -> None:
    """Mark a previously committed capture run as FAILED."""

    cursor.execute(
        """
        UPDATE catalog.schema_capture_run
        SET status_code = %s,
            ended_at = NOW(),
            updated_at = NOW()
        WHERE schema_capture_run_id = %s;
        """,
        (CAPTURE_STATUS_FAILED, capture_run_id),
    )


def main(dataset_id: int, binding_id: int) -> None:
    """Run metadata-driven schema capture for one configured dataset."""

   
    capture_run_id: int | None = None

    print_section("GENERIC SOURCE SCHEMA CAPTURE")
    print(f"Requested dataset ID : {dataset_id}")
    print(f"Requested binding ID : {binding_id}")

    # Resolve and validate the catalog dataset and binding.
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            catalog_context = get_dataset_catalog_context(
                cursor,
                dataset_id,
                binding_id,
            )

    # Resolve the source connection from the selected binding.
    connection_service = ConnectionService()
    connection_metadata = connection_service.get_connection_metadata(
        catalog_context["connection_id"]
    )

    print(f"Connection ID        : {connection_metadata.connection_id}")
    print(f"Connection Name      : {connection_metadata.connection_name}")
    print(f"Connector Code       : {connection_metadata.connector_code}")
    print(f"Connector Version ID : {connection_metadata.connector_version_id}")
    print(f"Source Database      : {catalog_context['catalog_name']}")
    print(f"Source Schema        : {catalog_context['schema_name']}")
    print(f"Source Object        : {catalog_context['object_name']}")

    # Create and commit the RUNNING capture record separately.
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            catalog_context = get_dataset_catalog_context(
                cursor,
                dataset_id,
                binding_id,
            )

            validate_schema_discovery_capability(
                cursor,
                connection_metadata.connector_version_id,
            )

            platform_id = resolve_platform_id(
                cursor,
                connection_metadata.connector_id,
            )

            capture_run_id = create_capture_run(
                cursor,
                catalog_context["tenant_id"],
                catalog_context["dataset_binding_id"],
                connection_metadata.connector_version_id,
            )

        connection.commit()

        print(f"Capture Run ID       : {capture_run_id}")
        print("Capture status       : RUNNING")

        try:
            print_section("PHYSICAL SCHEMA DISCOVERY")

            physical_columns = discover_source_columns(
                connection_metadata,
                catalog_context["schema_name"],
                catalog_context["object_name"],
            )

            normalized_columns = normalize_columns(physical_columns)

            for column in normalized_columns:
                print(
                    f"{column['ordinal_position']}. "
                    f"{column['field_name']} | "
                    f"{column['source_datatype_text']} | "
                    f"Nullable={column['is_nullable']}"
                )

            schema_hash = calculate_schema_hash(normalized_columns)
            print(f"Schema hash: {schema_hash}")

            print_section("CATALOG SCHEMA REGISTRATION")

            with connection.cursor() as cursor:
                existing_version_id = find_existing_schema_version(
                    cursor,
                    catalog_context["dataset_id"],
                    schema_hash,
                )

                if existing_version_id is not None:
                    complete_capture_run(cursor, capture_run_id)
                    connection.commit()

                    print("Schema is unchanged; no duplicate version created.")
                    print(f"Existing schema version ID: {existing_version_id}")
                    print("Status: COMPLETED")
                    return

                version_number = get_next_schema_version_number(
                    cursor,
                    catalog_context["dataset_id"],
                )

                schema_version_id = create_schema_version(
                    cursor,
                    catalog_context["tenant_id"],
                    catalog_context["dataset_id"],
                    catalog_context["dataset_binding_id"],
                    capture_run_id,
                    version_number,
                    schema_hash,
                    catalog_context["dataset_code"],
                )

                create_dataset_fields(
                    cursor,
                    catalog_context["tenant_id"],
                    schema_version_id,
                    platform_id,
                    normalized_columns,
                )

                complete_capture_run(cursor, capture_run_id)

            connection.commit()

            print_section("SCHEMA CAPTURE COMPLETED")
            print(f"Capture run ID    : {capture_run_id}")
            print(f"Schema version ID : {schema_version_id}")
            print(f"Schema version    : {version_number}")
            print(f"Fields captured   : {len(normalized_columns)}")
            print(f"Schema hash       : {schema_hash}")
            print("Status            : COMPLETED")

        except Exception:
            connection.rollback()
            print("Schema capture transaction rolled back.")

            if capture_run_id is not None:
                try:
                    with connection.cursor() as cursor:
                        fail_capture_run(cursor, capture_run_id)
                    connection.commit()
                    print(f"Capture run {capture_run_id} marked as FAILED.")
                except Exception:
                    connection.rollback()
                    print("Unable to persist FAILED capture-run status.")

            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Capture schema metadata for an existing catalog dataset "
            "and binding."
        )
    )

    parser.add_argument(
        "--dataset-id",
        type=int,
        required=True,
        help="Existing catalog dataset ID.",
    )

    parser.add_argument(
        "--binding-id",
        type=int,
        required=True,
        help="Existing catalog dataset binding ID.",
    )

    args = parser.parse_args()

    main(
        dataset_id=args.dataset_id,
        binding_id=args.binding_id,
    )
