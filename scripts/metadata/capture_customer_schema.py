"""
Customer Source Schema Capture

Purpose
-------
Capture the physical schema of:

    demo_source_db.public.customer

into the production-style catalog metadata model.

Current POC metadata:

    Connection ID : 1
    Dataset ID    : 7
    Binding ID    : 7
    Tenant ID     : 1
    Environment   : 1

Metadata written by this script:

    catalog.schema_capture_run
    catalog.dataset_schema_version
    catalog.dataset_field

High-level flow:

    Dynamic Connection 1
            |
            v
    PostgreSQL Connector
            |
            v
    Schema Discovery
            |
            v
    Physical Column Metadata
            |
            v
    PostgreSQL Native Datatype Resolution
            |
            v
    Schema Hash
            |
            v
    catalog.schema_capture_run
            |
            v
    catalog.dataset_schema_version
            |
            v
    catalog.dataset_field

Design principles
-----------------
1. Connection details come from metadata.
2. Credentials are resolved by the existing credential layer.
3. Connector capabilities are validated from metadata.
4. Dataset and binding are resolved from catalog metadata.
5. Native datatype IDs are resolved dynamically.
6. Database-generated identity IDs are never supplied manually.
7. Schema versions are idempotent using schema_hash.
8. Failed capture runs are retained with status FAILED.
9. Successful metadata changes are committed transactionally.
10. No legacy ingest.schema_* tables are used.

IMPORTANT
---------
This is the first REAL schema metadata write operation.
"""


# ============================================================================
# STANDARD LIBRARY IMPORTS
# ============================================================================

# hashlib is used to generate a deterministic SHA-256 schema hash.
import hashlib

# json is used to create a deterministic representation of the discovered
# schema before hashing it.
import json

# Any is used for flexible metadata structures returned by the connector.
from typing import Any


# ============================================================================
# THIRD-PARTY IMPORTS
# ============================================================================

# PostgreSQL driver used for database connection type hints.
import psycopg


# ============================================================================
# APPLICATION IMPORTS
# ============================================================================

# Centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection

# Connector registry stores supported connector implementations.
from app.connectors.registry import ConnectorRegistry

# Connector factory creates the correct connector from ConnectionMetadata.
from app.connectors.factory import ConnectorFactory

# PostgreSQL connector implementation.
from app.connectors.postgres.adapter import PostgreSQLConnector

# Connection service resolves dynamic connection metadata from conn.*.
from app.services.connection_service import ConnectionService


# ============================================================================
# POC CONSTANTS
# ============================================================================

# ---------------------------------------------------------------------------
# Current source connection.
#
# This is the authoritative dynamic source connection for the Customer POC.
# ---------------------------------------------------------------------------

SOURCE_CONNECTION_ID = 1


# ---------------------------------------------------------------------------
# Current catalog dataset.
#
# This dataset was registered specifically for the Customer POC.
# ---------------------------------------------------------------------------

CUSTOMER_DATASET_ID = 7


# ---------------------------------------------------------------------------
# Current catalog dataset binding.
#
# Binding 7 points to:
#
#     demo_source_db.public.customer
# ---------------------------------------------------------------------------

CUSTOMER_BINDING_ID = 7


# ---------------------------------------------------------------------------
# Required connector capability.
#
# The schema capture runtime must verify this capability before discovering
# the source schema.
# ---------------------------------------------------------------------------

REQUIRED_CAPABILITY_CODE = "SCHEMA_DISCOVERY"


# ---------------------------------------------------------------------------
# Capture mode used by catalog.schema_capture_run.
#
# This represents metadata discovery rather than a data load.
# ---------------------------------------------------------------------------

CAPTURE_MODE_CODE = "DISCOVERY"


# ---------------------------------------------------------------------------
# Initial capture status.
#
# The run is created as RUNNING before physical discovery begins.
# ---------------------------------------------------------------------------

CAPTURE_STATUS_RUNNING = "RUNNING"


# ---------------------------------------------------------------------------
# Successful capture status.
# ---------------------------------------------------------------------------

CAPTURE_STATUS_COMPLETED = "COMPLETED"


# ---------------------------------------------------------------------------
# Failed capture status.
# ---------------------------------------------------------------------------

CAPTURE_STATUS_FAILED = "FAILED"


# ============================================================================
# OUTPUT HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    Why:
    ----
    Schema capture is intentionally verbose during development so that
    each metadata operation can be demonstrated and validated.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# CONNECTOR REGISTRY
# ============================================================================

def create_connector_factory() -> ConnectorFactory:
    """
    Create the connector registry and factory used by the schema capture.

    Why:
    ----
    The schema capture engine should not instantiate PostgreSQL directly.

    Instead:

        ConnectionMetadata
                |
                v
        ConnectorFactory
                |
                v
        PostgreSQLConnector

    This allows the same schema capture workflow to support future
    MySQL, SQL Server, Oracle, Snowflake, etc. connectors.
    """

    # Create an empty connector registry.
    registry = ConnectorRegistry()

    # Register the PostgreSQL implementation.
    #
    # The connector code is metadata-driven and must match the connector
    # code stored in conn.connector.
    registry.register(
        "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
    )

    # Create the generic connector factory.
    factory = ConnectorFactory(registry)

    return factory


# ============================================================================
# VALIDATE DATASET AND BINDING
# ============================================================================

def get_customer_catalog_context(
    cursor: psycopg.Cursor,
) -> dict[str, Any]:
    """
    Validate Dataset 7 and Binding 7 and retrieve their metadata.

    Returns
    -------
    dict
        Dataset and binding information required by schema capture.
    """

    # ------------------------------------------------------------------------
    # Retrieve the dataset definition.
    # ------------------------------------------------------------------------

    dataset_query = """
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
    """

    # Execute the dataset lookup.
    cursor.execute(
        dataset_query,
        (CUSTOMER_DATASET_ID,),
    )

    # Retrieve the dataset record.
    dataset_record = cursor.fetchone()

    # Fail if the dataset is missing.
    if dataset_record is None:
        raise RuntimeError(
            f"Catalog dataset {CUSTOMER_DATASET_ID} was not found."
        )

    # Map the returned dataset values into a dictionary.
    (
        dataset_id,
        tenant_id,
        project_id,
        dataset_code,
        dataset_name,
        object_type_code,
        dataset_role_code,
        layer_code,
        status_code,
    ) = dataset_record

    # The Customer dataset must be active.
    if status_code != "ACTIVE":
        raise RuntimeError(
            f"Catalog dataset {dataset_id} is not ACTIVE."
        )

    # ------------------------------------------------------------------------
    # Retrieve the dataset binding.
    # ------------------------------------------------------------------------

    binding_query = """
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
    """

    # Execute the binding lookup.
    cursor.execute(
        binding_query,
        (
            CUSTOMER_BINDING_ID,
            CUSTOMER_DATASET_ID,
        ),
    )

    # Retrieve the binding record.
    binding_record = cursor.fetchone()

    # Fail if the binding is missing.
    if binding_record is None:
        raise RuntimeError(
            f"Catalog binding {CUSTOMER_BINDING_ID} was not found "
            f"for dataset {CUSTOMER_DATASET_ID}."
        )

    # Map the binding values.
    (
        dataset_binding_id,
        binding_tenant_id,
        binding_dataset_id,
        environment_id,
        connection_id,
        catalog_name,
        schema_name,
        object_name,
        object_name_normalized,
        binding_status_code,
    ) = binding_record

    # The binding must be active.
    if binding_status_code != "ACTIVE":
        raise RuntimeError(
            f"Catalog binding {dataset_binding_id} is not ACTIVE."
        )

    # The binding tenant must match the dataset tenant.
    if binding_tenant_id != tenant_id:
        raise RuntimeError(
            "Dataset and binding tenant IDs do not match."
        )

    # The binding must point to the authoritative Dynamic Connection 1.
    if connection_id != SOURCE_CONNECTION_ID:
        raise RuntimeError(
            "Customer dataset binding does not point to "
            f"Dynamic Connection {SOURCE_CONNECTION_ID}."
        )

    # Return the validated catalog context.
    return {
        "dataset_id": dataset_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "dataset_code": dataset_code,
        "dataset_name": dataset_name,
        "object_type_code": object_type_code,
        "dataset_role_code": dataset_role_code,
        "layer_code": layer_code,
        "dataset_binding_id": dataset_binding_id,
        "environment_id": environment_id,
        "connection_id": connection_id,
        "catalog_name": catalog_name,
        "schema_name": schema_name,
        "object_name": object_name,
        "object_name_normalized": object_name_normalized,
    }


# ============================================================================
# VALIDATE SCHEMA DISCOVERY CAPABILITY
# ============================================================================

def validate_schema_discovery_capability(
    cursor: psycopg.Cursor,
    connector_version_id: int,
) -> None:
    """
    Validate that the connector version supports SCHEMA_DISCOVERY.

    Why:
    ----
    Capability validation must come from metadata.

    We must not assume that every connector supports every operation.
    """

    # Resolve the capability and verify that it is explicitly supported.
    query = """
        SELECT
            connector_capability.capability_code,
            connector_version_capability.is_supported
        FROM conn.connector_version_capability
        INNER JOIN conn.connector_capability
            ON connector_capability.capability_id =
               connector_version_capability.capability_id
        WHERE connector_version_capability.connector_version_id = %s
          AND connector_capability.capability_code = %s;
    """

    # Execute the capability query.
    cursor.execute(
        query,
        (
            connector_version_id,
            REQUIRED_CAPABILITY_CODE,
        ),
    )

    # Retrieve the assignment.
    record = cursor.fetchone()

    # Fail if the capability assignment does not exist.
    if record is None:
        raise RuntimeError(
            "Required capability SCHEMA_DISCOVERY is not assigned "
            f"to connector version {connector_version_id}."
        )

    # Extract capability information.
    capability_code, is_supported = record

    # Fail if the connector explicitly reports the capability as unsupported.
    if is_supported is not True:
        raise RuntimeError(
            f"Capability {capability_code} is not supported by "
            f"connector version {connector_version_id}."
        )

    # Display successful validation.
    print(
        f"Capability validated: "
        f"{capability_code} = SUPPORTED"
    )


# ============================================================================
# RESOLVE PLATFORM ID
# ============================================================================

def resolve_platform_id(
    cursor: psycopg.Cursor,
    connector_id: int,
) -> int:
    """
    Resolve the database platform associated with a connector.

    Current relationship:

        conn.connector
              |
              | platform_id
              v
        conn.database_platform

    The runtime therefore does not hardcode PostgreSQL platform ID 3.
    """

    # Retrieve the platform ID from the connector definition.
    query = """
        SELECT
            platform_id
        FROM conn.connector
        WHERE connector_id = %s;
    """

    # Execute the lookup.
    cursor.execute(
        query,
        (connector_id,),
    )

    # Retrieve the platform ID.
    record = cursor.fetchone()

    # Fail if the connector does not exist.
    if record is None:
        raise RuntimeError(
            f"Connector {connector_id} was not found."
        )

    # Return the platform ID.
    return int(record[0])


# ============================================================================
# RESOLVE NATIVE DATATYPE
# ============================================================================

def resolve_native_datatype_id(
    cursor: psycopg.Cursor,
    platform_id: int,
    native_type_name: str,
) -> int:
    """
    Resolve a physical source datatype to dtype.native_datatype.

    Example:

        PostgreSQL INTEGER
            ->
        dtype.native_datatype

    Important:
    ---------
    The runtime does NOT hardcode:

        INTEGER = 62
        CHARACTER VARYING = 73

    It resolves the ID using metadata.

    If multiple active definitions exist for the same platform/type,
    the function fails rather than choosing one arbitrarily.

    This protects the runtime from ambiguous datatype metadata.
    """

    # Normalize the physical type name.
    normalized_type_name = (
        native_type_name
        .strip()
        .upper()
    )

    # Retrieve matching active native datatype definitions.
    query = """
        SELECT
            native_datatype_id,
            database_version_id,
            native_type_name
        FROM dtype.native_datatype
        WHERE platform_id = %s
          AND status_code = 'ACTIVE'
          AND UPPER(native_type_name) = %s
        ORDER BY database_version_id;
    """

    # Execute the metadata lookup.
    cursor.execute(
        query,
        (
            platform_id,
            normalized_type_name,
        ),
    )

    # Retrieve all matching records.
    records = cursor.fetchall()

    # Fail when no datatype metadata exists.
    if not records:
        raise RuntimeError(
            "No active native datatype metadata found for "
            f"platform {platform_id} and type "
            f"'{native_type_name}'."
        )

    # Fail when metadata is ambiguous.
    if len(records) > 1:
        raise RuntimeError(
            "Multiple active native datatype definitions found for "
            f"platform {platform_id} and type "
            f"'{native_type_name}'. "
            "Database-version-aware datatype resolution is required."
        )

    # Return the single unambiguous native datatype ID.
    return int(records[0][0])


# ============================================================================
# DISCOVER SOURCE SCHEMA
# ============================================================================

def discover_source_columns(
    connection_metadata: Any,
    schema_name: str,
    object_name: str,
) -> list[dict[str, Any]]:
    """
    Discover physical source columns using the dynamic connector.

    The connector implementation owns PostgreSQL-specific discovery logic.

    The metadata runtime only consumes the common connector contract.
    """

    # Create the generic connector factory.
    factory = create_connector_factory()

    # Create the appropriate connector from metadata.
    connector = factory.create(connection_metadata)

    try:
        # Establish the source database connection.
        connector.connect()

        # Discover the physical columns.
        columns = connector.list_columns(
            schema_name,
            object_name,
        )

        # Fail if the physical object has no columns.
        if not columns:
            raise RuntimeError(
                f"No columns were discovered for "
                f"{schema_name}.{object_name}."
            )

        return columns

    finally:
        # Always release the source connection.
        connector.close()


# ============================================================================
# NORMALIZE DISCOVERED COLUMNS
# ============================================================================

def normalize_columns(
    columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Normalize the connector's physical column metadata.

    The current PostgreSQL connector exposes:

        column_name
        data_type
        ordinal_position
        is_nullable
        column_default

    The catalog stores those values in a platform-neutral representation.
    """

    # Create the normalized list.
    normalized_columns: list[dict[str, Any]] = []

    # Process every discovered physical column.
    for column in columns:

        # Extract the column name.
        column_name = str(
            column["column_name"]
        ).strip()

        # Extract the physical datatype.
        data_type = str(
            column["data_type"]
        ).strip()

        # Normalize PostgreSQL's YES/NO nullable representation.
        nullable_value = column["is_nullable"]

        is_nullable = (
            str(nullable_value).upper() == "YES"
            if not isinstance(nullable_value, bool)
            else nullable_value
        )

        # Extract ordinal position.
        ordinal_position = int(
            column["ordinal_position"]
        )

        # Extract the default expression.
        default_expression = column.get(
            "column_default"
        )

        # Validate required physical metadata.
        if not column_name:
            raise RuntimeError(
                "Schema discovery returned a column with no name."
            )

        if not data_type:
            raise RuntimeError(
                f"Column '{column_name}' has no datatype."
            )

        # Add the normalized field definition.
        normalized_columns.append(
            {
                "ordinal_position": ordinal_position,
                "field_name": column_name,
                "field_name_normalized": column_name.lower(),
                "source_datatype_text": data_type,
                "is_nullable": is_nullable,
                "default_expression": default_expression,
            }
        )

    # Sort by physical ordinal position.
    normalized_columns.sort(
        key=lambda item: item["ordinal_position"]
    )

    return normalized_columns


# ============================================================================
# BUILD SCHEMA HASH
# ============================================================================

def calculate_schema_hash(
    columns: list[dict[str, Any]],
) -> str:
    """
    Calculate a deterministic SHA-256 hash for the discovered schema.

    The hash represents the structural metadata relevant to this capture.

    Why:
    ----
    Schema hashes allow the catalog to determine whether a newly discovered
    physical schema is identical to an existing schema version.

    The hash is NOT based on row data.
    """

    # Build a deterministic representation of the schema.
    schema_representation = []

    for column in columns:
        schema_representation.append(
            {
                "ordinal_position": column["ordinal_position"],
                "field_name": column["field_name"],
                "field_name_normalized": (
                    column["field_name_normalized"]
                ),
                "source_datatype_text": (
                    column["source_datatype_text"]
                ),
                "is_nullable": column["is_nullable"],
                "default_expression": (
                    column["default_expression"]
                ),
            }
        )

    # Convert the schema representation into deterministic JSON.
    canonical_json = json.dumps(
        schema_representation,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    # Generate SHA-256.
    schema_hash = hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()

    return schema_hash


# ============================================================================
# INSERT SCHEMA CAPTURE RUN
# ============================================================================

def create_capture_run(
    cursor: psycopg.Cursor,
    tenant_id: int,
    dataset_binding_id: int,
    connector_version_id: int,
) -> int:
    """
    Create a schema capture run.

    The primary key is generated by PostgreSQL identity generation.

    Therefore schema_capture_run_id is NOT supplied manually.
    """

    # Insert the capture run.
    query = """
        INSERT INTO catalog.schema_capture_run (
            tenant_id,
            dataset_binding_id,
            connector_version_id,
            capture_mode_code,
            status_code
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s
        )
        RETURNING schema_capture_run_id;
    """

    # Execute the insert.
    cursor.execute(
        query,
        (
            tenant_id,
            dataset_binding_id,
            connector_version_id,
            CAPTURE_MODE_CODE,
            CAPTURE_STATUS_RUNNING,
        ),
    )

    # Retrieve the database-generated identity.
    record = cursor.fetchone()

    # Defensive validation.
    if record is None:
        raise RuntimeError(
            "PostgreSQL did not return schema_capture_run_id."
        )

    return int(record[0])


# ============================================================================
# CHECK EXISTING SCHEMA HASH
# ============================================================================

def find_existing_schema_version(
    cursor: psycopg.Cursor,
    dataset_id: int,
    schema_hash: str,
) -> int | None:
    """
    Find an existing schema version with the same schema hash.

    The catalog has a unique constraint on:

        dataset_id + schema_hash

    Therefore an identical schema should reuse the existing version rather
    than creating duplicate metadata.
    """

    # Search for the existing schema hash.
    query = """
        SELECT
            schema_version_id
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s
          AND schema_hash = %s
        LIMIT 1;
    """

    # Execute the lookup.
    cursor.execute(
        query,
        (
            dataset_id,
            schema_hash,
        ),
    )

    # Retrieve the existing version.
    record = cursor.fetchone()

    # Return None when no matching schema exists.
    if record is None:
        return None

    return int(record[0])


# ============================================================================
# GET NEXT SCHEMA VERSION NUMBER
# ============================================================================

def get_next_schema_version_number(
    cursor: psycopg.Cursor,
    dataset_id: int,
) -> int:
    """
    Calculate the next schema version number.

    The first version is 1.

    Later versions increment from the current maximum.
    """

    # Retrieve the highest existing version number.
    query = """
        SELECT
            COALESCE(
                MAX(version_no),
                0
            )
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s;
    """

    # Execute the query.
    cursor.execute(
        query,
        (dataset_id,),
    )

    # Retrieve the maximum version.
    record = cursor.fetchone()

    # Calculate the next version.
    return int(record[0]) + 1


# ============================================================================
# INSERT SCHEMA VERSION
# ============================================================================

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
    """
    Create a new catalog schema version.

    The database generates schema_version_id automatically.
    """

    # Mark the previous current schema version as no longer current.
    #
    # This ensures only the new version is current for the dataset.
    update_current_query = """
        UPDATE catalog.dataset_schema_version
        SET
            is_current = FALSE,
            updated_at = NOW()
        WHERE dataset_id = %s
          AND is_current = TRUE;
    """

    # Execute the current-version update.
    cursor.execute(
        update_current_query,
        (dataset_id,),
    )

    # Insert the new schema version.
    insert_query = """
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
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            TRUE
        )
        RETURNING schema_version_id;
    """

    # Execute the insert.
    cursor.execute(
        insert_query,
        (
            tenant_id,
            dataset_id,
            binding_id,
            capture_run_id,
            version_number,
            schema_hash,
            source_code,
            "CREATE" if version_number == 1 else "ALTER",
        ),
    )

    # Retrieve the generated schema version ID.
    record = cursor.fetchone()

    # Defensive validation.
    if record is None:
        raise RuntimeError(
            "PostgreSQL did not return schema_version_id."
        )

    return int(record[0])


# ============================================================================
# INSERT DATASET FIELDS
# ============================================================================

def create_dataset_fields(
    cursor: psycopg.Cursor,
    tenant_id: int,
    schema_version_id: int,
    platform_id: int,
    columns: list[dict[str, Any]],
) -> None:
    """
    Insert the discovered fields into catalog.dataset_field.

    Each physical datatype is resolved through dtype.native_datatype.
    """

    # Insert every discovered source column.
    for column in columns:

        # Resolve the platform-neutral native datatype ID dynamically.
        native_datatype_id = resolve_native_datatype_id(
            cursor,
            platform_id,
            column["source_datatype_text"],
        )

        # Insert the field metadata.
        #
        # The primary key field_id is generated automatically by PostgreSQL.
        query = """
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
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NULL,
                NULL,
                NULL,
                %s,
                %s,
                FALSE,
                FALSE
            );
        """

        # Execute the field insert.
        cursor.execute(
            query,
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


# ============================================================================
# COMPLETE CAPTURE RUN
# ============================================================================

def complete_capture_run(
    cursor: psycopg.Cursor,
    capture_run_id: int,
) -> None:
    """
    Mark the schema capture run as completed.
    """

    # Update status and completion timestamp.
    query = """
        UPDATE catalog.schema_capture_run
        SET
            status_code = %s,
            ended_at = NOW(),
            updated_at = NOW()
        WHERE schema_capture_run_id = %s;
    """

    # Execute the completion update.
    cursor.execute(
        query,
        (
            CAPTURE_STATUS_COMPLETED,
            capture_run_id,
        ),
    )


# ============================================================================
# FAIL CAPTURE RUN
# ============================================================================

def fail_capture_run(
    cursor: psycopg.Cursor,
    capture_run_id: int,
) -> None:
    """
    Mark a previously created capture run as FAILED.

    This is deliberately performed in a separate transaction after a
    rollback so that the failed run remains visible as execution evidence.
    """

    # Update the capture run status.
    query = """
        UPDATE catalog.schema_capture_run
        SET
            status_code = %s,
            ended_at = NOW(),
            updated_at = NOW()
        WHERE schema_capture_run_id = %s;
    """

    # Execute the failure update.
    cursor.execute(
        query,
        (
            CAPTURE_STATUS_FAILED,
            capture_run_id,
        ),
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Execute Customer schema capture.

    Transaction design
    ------------------
    Phase 1:
        Validate metadata
        Create RUNNING capture record
        COMMIT

    Phase 2:
        Discover physical schema
        Resolve datatypes
        Create schema version
        Create fields
        Mark COMPLETED
        COMMIT

    Failure:
        ROLLBACK schema changes
        Mark existing capture run FAILED
        COMMIT failure evidence
    """

    # ------------------------------------------------------------------------
    # Script title.
    # ------------------------------------------------------------------------

    print_section(
        "CUSTOMER SOURCE SCHEMA CAPTURE"
    )

    # ------------------------------------------------------------------------
    # Resolve the dynamic source connection metadata.
    # ------------------------------------------------------------------------

    connection_service = ConnectionService()

    # Connection 1 is resolved from the metadata store.
    connection_metadata = (
        connection_service.get_connection_metadata(
            SOURCE_CONNECTION_ID
        )
    )

    # Display safe connection information.
    #
    # Passwords and secrets are intentionally never displayed.
    print(
        f"Connection ID   : "
        f"{connection_metadata.connection_id}"
    )

    print(
        f"Connection Name : "
        f"{connection_metadata.connection_name}"
    )

    print(
        f"Connector        : "
        f"{connection_metadata.connector_code}"
    )

    print(
        f"Connector Version: "
        f"{connection_metadata.connector_version_id}"
    )

    print(
        f"Database         : "
        f"{connection_metadata.database_name}"
    )

    # ------------------------------------------------------------------------
    # Open the metadata-store connection.
    # ------------------------------------------------------------------------

    with get_metastore_connection() as connection:

        capture_run_id: int | None = None

        try:
            # ================================================================
            # PHASE 1 — VALIDATION AND CAPTURE RUN
            # ================================================================

            print_section(
                "PHASE 1 - METADATA VALIDATION"
            )

            # Open a cursor for the validation transaction.
            with connection.cursor() as cursor:

                # Validate that the dataset and binding are correct.
                catalog_context = get_customer_catalog_context(
                    cursor
                )

                # Verify the connector capability.
                validate_schema_discovery_capability(
                    cursor,
                    connection_metadata.connector_version_id,
                )

                # Resolve the platform dynamically.
                platform_id = resolve_platform_id(
                    cursor,
                    connection_metadata.connector_id,
                )

                # Display catalog context.
                print(
                    f"Tenant ID       : "
                    f"{catalog_context['tenant_id']}"
                )

                print(
                    f"Dataset ID      : "
                    f"{catalog_context['dataset_id']}"
                )

                print(
                    f"Binding ID      : "
                    f"{catalog_context['dataset_binding_id']}"
                )

                print(
                    f"Environment ID  : "
                    f"{catalog_context['environment_id']}"
                )

                print(
                    f"Database        : "
                    f"{catalog_context['catalog_name']}"
                )

                print(
                    f"Schema          : "
                    f"{catalog_context['schema_name']}"
                )

                print(
                    f"Object          : "
                    f"{catalog_context['object_name']}"
                )

                print(
                    f"Platform ID     : "
                    f"{platform_id}"
                )

                # ------------------------------------------------------------
                # Create the execution evidence record.
                # ------------------------------------------------------------

                capture_run_id = create_capture_run(
                    cursor,
                    catalog_context["tenant_id"],
                    catalog_context["dataset_binding_id"],
                    connection_metadata.connector_version_id,
                )

                print()
                print(
                    f"Schema Capture Run ID: "
                    f"{capture_run_id}"
                )

            # Commit the RUNNING capture record.

            connection.commit()

            print(
                "Capture run created with status RUNNING."
            )

            # ================================================================
            # PHASE 2 — PHYSICAL SCHEMA DISCOVERY
            # ================================================================

            print_section(
                "PHASE 2 - PHYSICAL SCHEMA DISCOVERY"
            )

            # Discover physical source columns using the dynamic connector.
            physical_columns = discover_source_columns(
                connection_metadata,
                catalog_context["schema_name"],
                catalog_context["object_name"],
            )

            # Normalize the discovered metadata.
            normalized_columns = normalize_columns(
                physical_columns
            )

            # Display the discovered schema.
            print(
                f"Columns discovered: "
                f"{len(normalized_columns)}"
            )

            for column in normalized_columns:
                print(
                    f"{column['ordinal_position']}. "
                    f"{column['field_name']} | "
                    f"{column['source_datatype_text']} | "
                    f"Nullable={column['is_nullable']}"
                )

            # ================================================================
            # PHASE 3 — SCHEMA HASH
            # ================================================================

            print_section(
                "PHASE 3 - SCHEMA HASH"
            )

            # Calculate a deterministic structural hash.
            schema_hash = calculate_schema_hash(
                normalized_columns
            )

            print(
                f"Schema Hash: {schema_hash}"
            )

            # ================================================================
            # PHASE 4 — CATALOG WRITE
            # ================================================================

            print_section(
                "PHASE 4 - CATALOG SCHEMA VERSION"
            )

            # Open a new transaction for schema metadata.
            with connection.cursor() as cursor:

                # Check whether this exact schema already exists.
                existing_schema_version_id = (
                    find_existing_schema_version(
                        cursor,
                        catalog_context["dataset_id"],
                        schema_hash,
                    )
                )

                # ------------------------------------------------------------
                # Idempotent case.
                # ------------------------------------------------------------

                if existing_schema_version_id is not None:

                    print(
                        "Identical schema already exists."
                    )

                    print(
                        f"Existing Schema Version ID: "
                        f"{existing_schema_version_id}"
                    )

                    # No duplicate schema version or fields are created.
                    complete_capture_run(
                        cursor,
                        capture_run_id,
                    )

                    # Commit only the completed capture-run status.
                    connection.commit()

                    print()
                    print(
                        "Schema capture completed with "
                        "NO CHANGE."
                    )

                    return

                # ------------------------------------------------------------
                # New schema version.
                # ------------------------------------------------------------

                version_number = (
                    get_next_schema_version_number(
                        cursor,
                        catalog_context["dataset_id"],
                    )
                )

                print(
                    f"New Schema Version Number: "
                    f"{version_number}"
                )

                # Create the schema version.
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

                print(
                    f"Schema Version ID: "
                    f"{schema_version_id}"
                )

                # ============================================================
                # PHASE 5 — DATASET FIELDS
                # ============================================================

                print_section(
                    "PHASE 5 - DATASET FIELD REGISTRATION"
                )

                # Create catalog.dataset_field records.
                create_dataset_fields(
                    cursor,
                    catalog_context["tenant_id"],
                    schema_version_id,
                    platform_id,
                    normalized_columns,
                )

                # Display the number of field records created.
                print(
                    f"Dataset fields created: "
                    f"{len(normalized_columns)}"
                )

                # ------------------------------------------------------------
                # Mark the capture run as completed.
                # ------------------------------------------------------------

                complete_capture_run(
                    cursor,
                    capture_run_id,
                )

            # ================================================================
            # PHASE 6 — COMMIT
            # ================================================================

            # Commit schema version, fields and completed capture status
            # together as one transaction.
            connection.commit()

            print_section(
                "SCHEMA CAPTURE COMPLETED"
            )

            print(
                f"Capture Run ID       : {capture_run_id}"
            )

            print(
                f"Schema Version ID    : {schema_version_id}"
            )

            print(
                f"Schema Version       : {version_number}"
            )

            print(
                f"Fields Captured      : "
                f"{len(normalized_columns)}"
            )

            print(
                f"Schema Hash          : {schema_hash}"
            )

            print(
                "Status               : COMPLETED"
            )

        except Exception:
            # ================================================================
            # FAILURE HANDLING
            # ================================================================

            # Roll back any uncommitted schema metadata changes.
            connection.rollback()

            print()
            print(
                "Schema capture transaction rolled back."
            )

            # Preserve the capture-run evidence as FAILED.
            if capture_run_id is not None:

                try:
                    with connection.cursor() as cursor:

                        # Record the failed execution status.
                        fail_capture_run(
                            cursor,
                            capture_run_id,
                        )

                    # Commit the failure evidence.
                    connection.commit()

                    print(
                        f"Capture Run {capture_run_id} "
                        "marked as FAILED."
                    )

                except Exception:
                    # If even the failure-status update fails, roll back
                    # that secondary transaction as well.
                    connection.rollback()

                    print(
                        "Unable to persist FAILED capture-run status."
                    )

            # Re-raise the original exception so the terminal shows the
            # actual root cause.
            raise


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

# Execute the schema capture only when this module is run directly.
if __name__ == "__main__":
    main()