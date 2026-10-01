"""
Customer Target Physical Table Creation
========================================

Purpose
-------

This runtime script creates the physical target table for the
metadata-driven Customer full-load POC.

The script follows this sequence:

    1. Resolve target dataset and binding metadata.
    2. Read target schema version and target fields.
    3. Generate CREATE TABLE DDL from metadata.
    4. Resolve the target connection dynamically from conn.* tables.
    5. Resolve the correct connector through ConnectorFactory.
    6. Connect to the target PostgreSQL database.
    7. Create the target schema if required.
    8. Create the target table if it does not already exist.
    9. Verify the physical table against catalog metadata.

Important architectural principles
-----------------------------------

- No target password is hardcoded.
- No target host/database is hardcoded inside the connector.
- Connection metadata comes from conn.* metadata tables.
- Credential references are resolved through the credential layer.
- Connector selection is performed through ConnectorFactory.
- Target columns are generated from catalog.dataset_field.
- PostgreSQL-specific connection logic remains inside the PostgreSQL connector.
- Existing physical tables are never silently overwritten.
- All database writes are explicitly committed.
- Failed transactions are explicitly rolled back.

Current POC
-----------

Source:

    Connection ID : 1
    Database      : demo_source_db
    Schema        : public
    Table         : customer

Target:

    Connection ID : 11
    Database      : ingestion_metastore
    Schema        : warehouse
    Table         : customer_target

Target metadata:

    Dataset ID        : 8
    Binding ID        : 8
    Schema Version ID : 7

This script is intentionally focused on the current Customer POC.
Later, these constants should be replaced with runtime parameters
or an execution-plan resolver.
"""

# ---------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------

# dataclass is used to represent one target column in a type-safe way.
from dataclasses import dataclass


# ---------------------------------------------------------------------
# Third-party imports
# ---------------------------------------------------------------------

# psycopg provides the PostgreSQL connection and database execution API.
import psycopg


# ---------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------

# ConnectorFactory creates the correct connector implementation
# based on connector metadata.
from app.connectors.factory import ConnectorFactory

# The connector registry registers the available connector
# implementations.
from app.connectors.register_connectors import (
    create_connector_registry,
)

# The metadata database connection manager opens a connection
# to the control-plane metadata database.
from app.db.metastore import get_metastore_connection

# ConnectionMetadata represents the platform-neutral runtime
# connection configuration.
#
# ConnectionParameter represents one dynamic connection parameter.
#
# Both classes are required because ConnectionMetadata.parameters
# expects:
#
#     dict[str, ConnectionParameter]
#
# and not a simple dictionary of strings.
from app.models.connection import (
    ConnectionMetadata,
    ConnectionParameter,
)


# ---------------------------------------------------------------------
# POC metadata identifiers
# ---------------------------------------------------------------------

# Target dataset already registered in catalog.dataset.
TARGET_DATASET_ID = 8

# Target physical binding already registered in catalog.dataset_binding.
TARGET_BINDING_ID = 8

# Target schema version already registered in
# catalog.dataset_schema_version.
TARGET_SCHEMA_VERSION_ID = 7

# Target connection already registered in conn.connection_profile.
TARGET_CONNECTION_ID = 11


# ---------------------------------------------------------------------
# Target physical location
# ---------------------------------------------------------------------

# These values are used only as validation guards for this POC.
#
# The authoritative metadata is still read from
# catalog.dataset_binding.
EXPECTED_TARGET_DATABASE = "ingestion_metastore"
EXPECTED_TARGET_SCHEMA = "warehouse"
EXPECTED_TARGET_TABLE = "customer_target"


# ---------------------------------------------------------------------
# Target column model
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class TargetColumn:
    """
    Represents one target column derived from catalog metadata.

    The physical table should be generated from metadata rather than
    from hardcoded column definitions.
    """

    # Physical column name.
    column_name: str

    # Native database datatype text used by the target database.
    data_type: str

    # Whether the target column accepts NULL values.
    is_nullable: bool

    # Optional default expression captured in metadata.
    default_expression: str | None = None

    # Indicates whether the column is an identity column.
    is_identity: bool = False

    # Indicates whether the column is generated by the database.
    is_generated: bool = False


# ---------------------------------------------------------------------
# Identifier quoting
# ---------------------------------------------------------------------

def quote_identifier(identifier: str) -> str:
    """
    Safely quote a PostgreSQL identifier.

    Why this is required
    --------------------

    Schema names, table names and column names come from metadata.

    They must therefore be quoted instead of concatenated into SQL
    without escaping.

    PostgreSQL escapes a double quote inside an identifier by
    representing it as two double quotes.
    """

    # Validate that an identifier was actually supplied.
    if identifier is None or not str(identifier).strip():
        raise ValueError(
            "SQL identifier cannot be empty."
        )

    # Escape any embedded double quotes.
    escaped_identifier = str(identifier).replace(
        '"',
        '""',
    )

    # Return the PostgreSQL quoted identifier.
    return f'"{escaped_identifier}"'


# ---------------------------------------------------------------------
# Target binding resolution
# ---------------------------------------------------------------------

def get_target_binding(
    connection: psycopg.Connection,
) -> dict:
    """
    Resolve the target dataset binding from catalog.dataset_binding.

    The binding is the authoritative metadata describing where the
    physical target object should exist.
    """

    # Query the target binding together with dataset information.
    query = """
        SELECT
            db.dataset_binding_id,
            db.tenant_id,
            db.dataset_id,
            db.environment_id,
            db.connection_id,
            db.catalog_name,
            db.schema_name,
            db.object_name,
            db.object_name_normalized,
            db.status_code,

            d.project_id,
            d.dataset_code,
            d.dataset_name,
            d.object_type_code,
            d.dataset_role_code,
            d.layer_code,
            d.status_code

        FROM catalog.dataset_binding AS db

        INNER JOIN catalog.dataset AS d
            ON d.dataset_id = db.dataset_id

        WHERE db.dataset_binding_id = %s
          AND db.dataset_id = %s

        LIMIT 1;
    """

    # Read the target binding from the metadata store.
    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                TARGET_BINDING_ID,
                TARGET_DATASET_ID,
            ),
        )

        row = cursor.fetchone()

    # Fail immediately if the expected metadata does not exist.
    if row is None:
        raise LookupError(
            "Target dataset binding was not found. "
            f"Dataset ID={TARGET_DATASET_ID}, "
            f"Binding ID={TARGET_BINDING_ID}"
        )

    # Convert the result into a dictionary so that the calling
    # code can access fields by meaningful names.
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
        "binding_status": row[9],
        "project_id": row[10],
        "dataset_code": row[11],
        "dataset_name": row[12],
        "object_type_code": row[13],
        "dataset_role_code": row[14],
        "layer_code": row[15],
        "dataset_status": row[16],
    }


# ---------------------------------------------------------------------
# Target field resolution
# ---------------------------------------------------------------------

def get_target_fields(
    connection: psycopg.Connection,
) -> list[TargetColumn]:
    """
    Read target fields from catalog.dataset_field.

    Native datatype information is resolved from dtype.native_datatype.

    This means the target DDL is derived from the metadata model instead
    of being manually written into this script.
    """

    # Read target fields belonging to the registered target schema
    # version.
    query = """
        SELECT
            df.ordinal_no,
            df.field_name,
            df.source_datatype_text,
            df.is_nullable,
            df.default_expression,
            df.is_identity,
            df.is_generated,
            nd.native_type_name

        FROM catalog.dataset_field AS df

        INNER JOIN dtype.native_datatype AS nd
            ON nd.native_datatype_id = df.native_datatype_id

        WHERE df.schema_version_id = %s

        ORDER BY df.ordinal_no;
    """

    # Execute the metadata query.
    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (TARGET_SCHEMA_VERSION_ID,),
        )

        rows = cursor.fetchall()

    # A target schema without fields cannot produce a valid table.
    if not rows:
        raise LookupError(
            "No target fields were found for schema version "
            f"{TARGET_SCHEMA_VERSION_ID}."
        )

    # Store the resulting target fields.
    target_fields: list[TargetColumn] = []

    # Convert each metadata row into a TargetColumn object.
    for row in rows:

        (
            ordinal_no,
            field_name,
            source_datatype_text,
            is_nullable,
            default_expression,
            is_identity,
            is_generated,
            native_type_name,
        ) = row

        # Prefer the registered native datatype name from
        # dtype.native_datatype.
        #
        # The source_datatype_text is retained in metadata but is not
        # used as the authoritative physical datatype when the native
        # datatype catalogue provides the value.
        data_type = native_type_name

        # Validate that the metadata contains a datatype.
        if not data_type:
            raise ValueError(
                f"Target field {field_name!r} has no native datatype."
            )

        # Create the platform-neutral target field object.
        target_fields.append(
            TargetColumn(
                column_name=field_name,
                data_type=data_type,
                is_nullable=bool(is_nullable),
                default_expression=default_expression,
                is_identity=bool(is_identity),
                is_generated=bool(is_generated),
            )
        )

    return target_fields


# ---------------------------------------------------------------------
# Target DDL generation
# ---------------------------------------------------------------------

def generate_create_table_ddl(
    schema_name: str,
    table_name: str,
    target_fields: list[TargetColumn],
) -> str:
    """
    Generate CREATE TABLE DDL from target metadata.

    The DDL is generated only after the metadata has been validated.
    """

    # Validate that at least one field exists.
    if not target_fields:
        raise ValueError(
            "Cannot generate target DDL because no fields exist."
        )

    # Store each generated column definition.
    column_definitions: list[str] = []

    # Generate the physical SQL definition for every target field.
    for field in target_fields:

        # Start with quoted column name and native datatype.
        definition = (
            f"{quote_identifier(field.column_name)} "
            f"{field.data_type}"
        )

        # Apply NOT NULL based on catalog metadata.
        if not field.is_nullable:
            definition += " NOT NULL"

        # Apply a default expression only when metadata explicitly
        # contains one.
        #
        # The expression is treated as database-native metadata and
        # therefore is not quoted as a string.
        if field.default_expression:
            definition += (
                f" DEFAULT {field.default_expression}"
            )

        # Identity/generated semantics are deliberately not added
        # automatically in this POC because the current Customer target
        # fields do not use them.
        #
        # They should be implemented centrally in the generic DDL
        # generator once identity/generated mappings are finalized.

        column_definitions.append(definition)

    # Join all columns with commas and indentation.
    columns_sql = ",\n    ".join(
        column_definitions
    )

    # Build the complete CREATE TABLE statement.
    ddl = (
        f"CREATE TABLE "
        f"{quote_identifier(schema_name)}."
        f"{quote_identifier(table_name)} (\n"
        f"    {columns_sql}\n"
        f");"
    )

    return ddl


# ---------------------------------------------------------------------
# Physical table existence check
# ---------------------------------------------------------------------

def physical_table_exists(
    connection: psycopg.Connection,
    schema_name: str,
    table_name: str,
) -> bool:
    """
    Check whether the target table already exists.

    information_schema is used because it provides a portable metadata
    interface for relational databases.

    The actual connector remains responsible for database-specific
    operations.
    """

    # Query the PostgreSQL information schema.
    query = """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name = %s
        );
    """

    # Execute the existence check.
    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                schema_name,
                table_name,
            ),
        )

        row = cursor.fetchone()

    # Return the boolean result.
    return bool(row[0])


# ---------------------------------------------------------------------
# Target schema creation
# ---------------------------------------------------------------------

def create_target_schema(
    connection: psycopg.Connection,
    schema_name: str,
) -> None:
    """
    Create the target schema when it does not already exist.

    CREATE SCHEMA IF NOT EXISTS makes the operation idempotent.
    """

    # Quote the schema name because it originates from metadata.
    quoted_schema = quote_identifier(schema_name)

    # Create the schema only when necessary.
    ddl = (
        f"CREATE SCHEMA IF NOT EXISTS "
        f"{quoted_schema};"
    )

    try:

        # Execute the schema creation statement.
        with connection.cursor() as cursor:
            cursor.execute(ddl)

        # Commit the schema creation.
        connection.commit()

    except Exception:

        # Roll back the transaction if schema creation fails.
        connection.rollback()

        # Re-raise the original exception.
        raise


# ---------------------------------------------------------------------
# Physical target verification
# ---------------------------------------------------------------------

def verify_physical_target(
    connection: psycopg.Connection,
    schema_name: str,
    table_name: str,
    target_fields: list[TargetColumn],
) -> None:
    """
    Verify the physical target table against catalog metadata.

    The verification checks:

        - physical column count
        - column names
        - physical datatype
        - nullability

    This is an important metadata/runtime consistency check.
    """

    # Read physical column metadata from PostgreSQL.
    query = """
        SELECT
            column_name,
            data_type,
            is_nullable,
            ordinal_position

        FROM information_schema.columns

        WHERE table_schema = %s
          AND table_name = %s

        ORDER BY ordinal_position;
    """

    # Execute the physical metadata query.
    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                schema_name,
                table_name,
            ),
        )

        physical_rows = cursor.fetchall()

    # Verify that the physical table exists.
    if not physical_rows:
        raise RuntimeError(
            "Target table exists check passed unexpectedly, "
            "but no physical columns were found for "
            f"{schema_name}.{table_name}."
        )

    # Compare physical and metadata field counts.
    if len(physical_rows) != len(target_fields):
        raise RuntimeError(
            "Target physical column count does not match metadata. "
            f"Physical={len(physical_rows)}, "
            f"Metadata={len(target_fields)}."
        )

    # Compare every field in ordinal order.
    for index, (
        physical_row,
        metadata_field,
    ) in enumerate(
        zip(
            physical_rows,
            target_fields,
            strict=True,
        ),
        start=1,
    ):

        (
            physical_name,
            physical_type,
            physical_nullable,
            physical_ordinal,
        ) = physical_row

        # Validate column name.
        if physical_name != metadata_field.column_name:
            raise RuntimeError(
                "Target column name mismatch at ordinal "
                f"{index}. "
                f"Physical={physical_name!r}, "
                f"Metadata={metadata_field.column_name!r}."
            )

        # Compare PostgreSQL datatype text case-insensitively.
        #
        # information_schema generally returns values such as:
        #
        #     integer
        #     character varying
        #
        # The metadata catalogue can contain uppercase/native casing.
        physical_type_normalized = (
            str(physical_type).strip().lower()
        )

        metadata_type_normalized = (
            str(metadata_field.data_type).strip().lower()
        )

        if physical_type_normalized != metadata_type_normalized:
            raise RuntimeError(
                "Target datatype mismatch for column "
                f"{metadata_field.column_name!r}. "
                f"Physical={physical_type!r}, "
                f"Metadata={metadata_field.data_type!r}."
            )

        # Convert information_schema's YES/NO representation to a
        # boolean for comparison.
        physical_is_nullable = (
            str(physical_nullable).upper() == "YES"
        )

        # Validate nullability.
        if physical_is_nullable != metadata_field.is_nullable:
            raise RuntimeError(
                "Target nullability mismatch for column "
                f"{metadata_field.column_name!r}. "
                f"Physical={physical_nullable!r}, "
                f"Metadata={metadata_field.is_nullable!r}."
            )

    # If execution reaches this point, the physical target is aligned
    # with the current POC metadata.
    print(
        "Physical target verification: PASSED"
    )


# ---------------------------------------------------------------------
# Target connection metadata resolution
# ---------------------------------------------------------------------

def get_target_connection_metadata(
    connection: psycopg.Connection,
) -> ConnectionMetadata:
    """
    Resolve target connection metadata from the authoritative conn.*
    metadata tables.

    Important
    ---------

    conn.connection_profile contains additional control-plane fields
    such as:

        tenant_id
        system_id
        environment_id

    Those fields are intentionally NOT passed into ConnectionMetadata
    because ConnectionMetadata does not define them.

    ConnectionMetadata contains only the runtime information required
    by ConnectorFactory and the connector implementation.
    """

    # -----------------------------------------------------------------
    # Resolve the target connection profile
    # -----------------------------------------------------------------

    # Read the complete connection profile together with connector
    # catalogue/version information.
    profile_query = """
        SELECT
            cp.connection_id,
            cp.connection_name,
            cp.connector_version_id,

            cv.connector_id,
            cv.semantic_version,

            c.connector_code,
            c.connector_name,

            cp.credential_id,
            cp.connection_role_code,

            cp.host_name,
            cp.port_no,
            cp.database_name,
            cp.endpoint_url,

            cp.connect_timeout_seconds,
            cp.command_timeout_seconds

        FROM conn.connection_profile AS cp

        INNER JOIN conn.connector_version AS cv
            ON cv.connector_version_id =
               cp.connector_version_id

        INNER JOIN conn.connector AS c
            ON c.connector_id =
               cv.connector_id

        WHERE cp.connection_id = %s

        LIMIT 1;
    """

    # Execute the profile lookup.
    with connection.cursor() as cursor:

        cursor.execute(
            profile_query,
            (TARGET_CONNECTION_ID,),
        )

        profile = cursor.fetchone()

    # Fail if the target connection cannot be resolved.
    if profile is None:
        raise LookupError(
            "Target connection was not found in "
            "conn.connection_profile. "
            f"Connection ID={TARGET_CONNECTION_ID}"
        )

    # Unpack the profile metadata.
    (
        connection_id,
        connection_name,
        connector_version_id,
        connector_id,
        connector_version,
        connector_code,
        connector_name,
        credential_id,
        connection_role_code,
        host_name,
        port_no,
        database_name,
        endpoint_url,
        connect_timeout_seconds,
        command_timeout_seconds,
    ) = profile

    # -----------------------------------------------------------------
    # Validate the connection role
    # -----------------------------------------------------------------

    # This script is responsible for target creation, therefore the
    # connection must be TARGET or BOTH.
    if connection_role_code.upper() not in {
        "TARGET",
        "BOTH",
    }:
        raise ValueError(
            "The resolved connection cannot be used as a target. "
            f"Connection ID={connection_id}, "
            f"Role={connection_role_code!r}"
        )

    # -----------------------------------------------------------------
    # Resolve dynamic connection parameters
    # -----------------------------------------------------------------

    # Dynamic parameters are stored separately from the connection
    # profile.
    parameter_query = """
        SELECT
            parameter_name,
            parameter_value,
            value_type_code,
            is_secret_ref

        FROM conn.connection_parameter

        WHERE connection_id = %s

        ORDER BY parameter_name;
    """

    # Start with an empty platform-neutral parameter dictionary.
    parameters: dict[str, ConnectionParameter] = {}

    # Read all parameters belonging to the target connection.
    with connection.cursor() as cursor:

        cursor.execute(
            parameter_query,
            (connection_id,),
        )

        parameter_rows = cursor.fetchall()

    # Convert each database row into a ConnectionParameter object.
    for (
        parameter_name,
        parameter_value,
        value_type_code,
        is_secret_ref,
    ) in parameter_rows:

        # Do not resolve secrets here.
        #
        # If a parameter is marked as a secret reference, the connector
        # or credential layer is responsible for resolving it.
        parameter = ConnectionParameter(
            name=parameter_name,
            value=parameter_value,
            value_type=value_type_code,
            is_secret_ref=bool(is_secret_ref),
        )

        # Store the object by parameter name.
        parameters[parameter_name] = parameter

    # -----------------------------------------------------------------
    # Build runtime ConnectionMetadata
    # -----------------------------------------------------------------

    # IMPORTANT:
    #
    # tenant_id
    # system_id
    # environment_id
    #
    # are deliberately not passed here because they are not constructor
    # arguments of ConnectionMetadata.
    return ConnectionMetadata(
        connection_id=connection_id,
        connection_name=connection_name,
        connector_id=connector_id,
        connector_code=connector_code,
        connector_name=connector_name,
        connector_version_id=connector_version_id,
        connector_version=connector_version,
        host_name=host_name,
        port_no=port_no,
        database_name=database_name,
        endpoint_url=endpoint_url,
        credential_id=credential_id,
        connection_role_code=connection_role_code,
        connect_timeout_seconds=connect_timeout_seconds,
        command_timeout_seconds=command_timeout_seconds,
        parameters=parameters,
    )


# ---------------------------------------------------------------------
# Main runtime workflow
# ---------------------------------------------------------------------

def main() -> None:
    """
    Execute the complete target physical table creation workflow.
    """

    # Display the runtime process header.
    print("=" * 72)
    print("CUSTOMER TARGET PHYSICAL TABLE CREATION")
    print("=" * 72)

    # -----------------------------------------------------------------
    # Connect to the metadata/control database
    # -----------------------------------------------------------------

    with get_metastore_connection() as metastore_connection:

        # =============================================================
        # PHASE 1 - TARGET METADATA
        # =============================================================

        print()
        print("PHASE 1 - TARGET METADATA")
        print("-" * 72)

        # Resolve the target dataset binding.
        target_binding = get_target_binding(
            metastore_connection
        )

        # Extract the physical target location from metadata.
        target_database = EXPECTED_TARGET_DATABASE
        target_schema = target_binding["schema_name"]
        target_table = target_binding["object_name"]

        # Validate the expected POC location.
        if target_schema != EXPECTED_TARGET_SCHEMA:
            raise ValueError(
                "Target schema does not match the expected POC "
                f"location. "
                f"Metadata={target_schema!r}, "
                f"Expected={EXPECTED_TARGET_SCHEMA!r}"
            )

        if target_table != EXPECTED_TARGET_TABLE:
            raise ValueError(
                "Target table does not match the expected POC "
                f"location. "
                f"Metadata={target_table!r}, "
                f"Expected={EXPECTED_TARGET_TABLE!r}"
            )

        # Validate that the binding points to the intended target
        # connection.
        if (
            target_binding["connection_id"]
            != TARGET_CONNECTION_ID
        ):
            raise ValueError(
                "Target binding points to an unexpected connection. "
                f"Binding Connection ID="
                f"{target_binding['connection_id']}, "
                f"Expected={TARGET_CONNECTION_ID}"
            )

        # Display validated target metadata.
        print(
            f"Dataset ID       : "
            f"{target_binding['dataset_id']}"
        )

        print(
            f"Binding ID       : "
            f"{target_binding['dataset_binding_id']}"
        )

        print(
            f"Connection ID    : "
            f"{target_binding['connection_id']}"
        )

        print(
            f"Database         : "
            f"{target_database}"
        )

        print(
            f"Schema           : "
            f"{target_schema}"
        )

        print(
            f"Table            : "
            f"{target_table}"
        )

        # Resolve target fields from the registered schema version.
        target_fields = get_target_fields(
            metastore_connection
        )

        print(
            f"Target Fields    : "
            f"{len(target_fields)}"
        )

        # =============================================================
        # PHASE 2 - GENERATED TARGET DDL
        # =============================================================

        print()
        print("PHASE 2 - GENERATED TARGET DDL")
        print("-" * 72)

        # Generate the target CREATE TABLE statement entirely from
        # catalog metadata.
        create_table_ddl = generate_create_table_ddl(
            schema_name=target_schema,
            table_name=target_table,
            target_fields=target_fields,
        )

        # Display the generated DDL.
        print(create_table_ddl)

        # =============================================================
        # PHASE 3 - TARGET CONNECTION RESOLUTION
        # =============================================================

        print()
        print("PHASE 3 - TARGET CONNECTION RESOLUTION")
        print("-" * 72)

        # Resolve target connection metadata from conn.* tables.
        connection_metadata = get_target_connection_metadata(
            metastore_connection
        )

        # Display non-secret connection information.
        #
        # Passwords and other secret values are deliberately not
        # printed.
        print(
            f"Connection ID    : "
            f"{connection_metadata.connection_id}"
        )

        print(
            f"Connection Name  : "
            f"{connection_metadata.connection_name}"
        )

        print(
            f"Connector        : "
            f"{connection_metadata.connector_code}"
        )

        print(
            f"Connector Version: "
            f"{connection_metadata.connector_version}"
        )

        print(
            f"Role             : "
            f"{connection_metadata.connection_role_code}"
        )

        print(
            f"Host             : "
            f"{connection_metadata.host_name}"
        )

        print(
            f"Port             : "
            f"{connection_metadata.port_no}"
        )

        print(
            f"Database         : "
            f"{connection_metadata.database_name}"
        )

        # =============================================================
        # PHASE 4 - CONNECTOR RESOLUTION
        # =============================================================

        print()
        print("PHASE 4 - CONNECTOR RESOLUTION")
        print("-" * 72)

        # Create the connector registry.
        #
        # The registry contains the supported connector implementations.
        registry = create_connector_registry()

        # Create the factory using the registry.
        factory = ConnectorFactory(
            registry
        )

        # Resolve the actual connector implementation from metadata.
        connector = factory.create(
            connection_metadata
        )

        # Display the selected connector.
        print(
            "Connector instance resolved successfully."
        )

        print(
            f"Connector Code   : "
            f"{connection_metadata.connector_code}"
        )

        # =============================================================
        # PHASE 5 - TARGET PHYSICAL CONNECTION
        # =============================================================

        print()
        print("PHASE 5 - TARGET PHYSICAL CONNECTION")
        print("-" * 72)

        # Open the physical target database connection through the
        # connector abstraction.
        #
        # The PostgreSQL-specific implementation is hidden behind
        # the connector interface.
        target_connection = connector.connect()

        try:

            # Display successful connection status.
            print(
                "Target database connection established."
            )

            # =========================================================
            # PHASE 6 - TARGET SCHEMA
            # =========================================================

            print()
            print("PHASE 6 - TARGET SCHEMA")
            print("-" * 72)

            # Create the target schema when required.
            create_target_schema(
                target_connection,
                target_schema,
            )

            print(
                f"Target schema verified/created: "
                f"{target_schema}"
            )

            # =========================================================
            # PHASE 7 - TARGET TABLE
            # =========================================================

            print()
            print("PHASE 7 - TARGET TABLE")
            print("-" * 72)

            # Check whether the target table already exists.
            table_exists = physical_table_exists(
                target_connection,
                target_schema,
                target_table,
            )

            # ---------------------------------------------------------
            # Existing table
            # ---------------------------------------------------------

            if table_exists:

                # Never silently drop or overwrite an existing target
                # table in this runtime.
                print(
                    f"Target table already exists: "
                    f"{target_schema}.{target_table}"
                )

                print(
                    "No CREATE TABLE operation will be performed."
                )

                # Verify the existing physical table against metadata.
                verify_physical_target(
                    target_connection,
                    target_schema,
                    target_table,
                    target_fields,
                )

            # ---------------------------------------------------------
            # New table
            # ---------------------------------------------------------

            else:

                # Create the physical target table from generated DDL.
                print(
                    "Target table does not exist."
                )

                print(
                    "Creating physical target table..."
                )

                try:

                    # Execute the metadata-generated CREATE TABLE DDL.
                    with target_connection.cursor() as cursor:
                        cursor.execute(
                            create_table_ddl
                        )

                    # Commit the physical table creation.
                    target_connection.commit()

                    print(
                        "Target table created successfully."
                    )

                except Exception:

                    # Roll back the failed target table transaction.
                    target_connection.rollback()

                    # Re-raise the original exception so the runtime
                    # does not report a false success.
                    raise

                # Verify the newly created physical table.
                verify_physical_target(
                    target_connection,
                    target_schema,
                    target_table,
                    target_fields,
                )

        finally:

            # Always close the physical target database connection.
            #
            # This prevents leaked connections even when table creation
            # or verification fails.
            target_connection.close()

            print(
                "Target database connection closed."
            )

    # -----------------------------------------------------------------
    # Completion
    # -----------------------------------------------------------------

    print()
    print("=" * 72)
    print("PHYSICAL TARGET TABLE CREATION COMPLETED")
    print("=" * 72)

    print(
        f"Physical Location : "
        f"{target_database}.{target_schema}.{target_table}"
    )

    print(
        f"Target Dataset ID : "
        f"{TARGET_DATASET_ID}"
    )

    print(
        f"Target Binding ID : "
        f"{TARGET_BINDING_ID}"
    )

    print(
        f"Schema Version ID : "
        f"{TARGET_SCHEMA_VERSION_ID}"
    )

    print(
        f"Target Connection : "
        f"{TARGET_CONNECTION_ID}"
    )

    print(
        "Metadata-driven target creation: PASSED"
    )


# ---------------------------------------------------------------------
# Python module entry point
# ---------------------------------------------------------------------

if __name__ == "__main__":
    """
    Run the target creation workflow when this file is executed as:

        python -m scripts.runtime.create_customer_target_table
    """

    main()