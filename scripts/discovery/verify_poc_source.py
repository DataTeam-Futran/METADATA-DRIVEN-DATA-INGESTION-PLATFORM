"""
POC Source Verification
=======================

This script verifies that the metadata-driven source configuration
can be resolved end-to-end and that the dynamically selected source
connector can actually discover the expected source database objects.

Purpose
-------

The verification flow is:

    Published Mapping Version
            |
            v
    MetadataResolver
            |
            v
    Source Metadata
            |
            v
    ConnectionService
            |
            v
    Dynamic Connection Metadata
            |
            v
    ConnectorFactory
            |
            v
    PostgreSQLConnector
            |
            v
    Source Database
            |
            +--> Schema discovery
            |
            +--> Table discovery

This script is READ-ONLY.

It does not:

    - insert metadata
    - update metadata
    - delete metadata
    - create source tables
    - create target tables
    - modify source data
    - modify target data
    - print passwords or secrets

Why this script is important
-----------------------------

Before implementing the actual ingestion engine, we need to prove
that the metadata and connector layers can correctly identify the
physical source object.

For the current POC:

    Metadata says:

        source_db.public.employee

    Dynamic connection metadata says:

        demo_source_db

The script therefore verifies whether the dynamic connection can
actually discover the expected schema/table.

If the metadata and physical connection point to different databases,
the script will make that mismatch visible instead of silently
changing configuration.
"""


from __future__ import annotations

from app.connectors.base import BaseConnector
from app.connectors.factory import ConnectorFactory
from app.connectors.registry import ConnectorRegistry
from app.connectors.postgres.adapter import PostgreSQLConnector
from app.metadata.resolver import MetadataResolver
from app.services.connection_service import ConnectionService


# ---------------------------------------------------------------------------
# POC CONFIGURATION
# ---------------------------------------------------------------------------
# Mapping version 1 is the currently published employee mapping used
# by the POC metadata.
#
# Keeping this as a constant makes the verification target explicit
# and easy to change later when another published mapping is tested.
POC_MAPPING_VERSION_ID = 1


# ---------------------------------------------------------------------------
# CONNECTOR REGISTRY CREATION
# ---------------------------------------------------------------------------
def create_registry() -> ConnectorRegistry:
    """
    Create the connector registry used by the POC.

    WHY
    ---
    The registry provides a database-independent way to select the
    correct connector implementation.

    For example:

        POSTGRESQL_CONNECTOR
                |
                v
        PostgreSQLConnector

    Later, additional connectors can be registered here:

        MYSQL_CONNECTOR
        SQL_SERVER_CONNECTOR
        ORACLE_CONNECTOR
        SNOWFLAKE_CONNECTOR
        etc.

    The current POC only registers PostgreSQL because that is the
    connector being implemented and tested first.

    Returns
    -------
    ConnectorRegistry
        Registry containing the supported POC connectors.
    """

    # Create an empty registry.
    registry = ConnectorRegistry()

    # Register the PostgreSQL implementation against the metadata
    # connector code used by conn.connector.
    registry.register(
        "POSTGRESQL_CONNECTOR",
        PostgreSQLConnector,
    )

    return registry


# ---------------------------------------------------------------------------
# DISPLAY HELPERS
# ---------------------------------------------------------------------------
def print_section(title: str) -> None:
    """
    Print a consistent section header.

    WHY
    ---
    This is only a console formatting helper. It keeps the verification
    output easy to read during development and debugging.
    """

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_subsection(title: str) -> None:
    """
    Print a smaller subsection header.

    WHY
    ---
    The verification script performs several independent checks.
    Subsections make the execution flow visible in the terminal.
    """

    print()
    print(title)
    print("-" * 80)


# ---------------------------------------------------------------------------
# MAIN VERIFICATION FLOW
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Execute the complete source verification flow.

    The verification is intentionally read-only.

    The method validates:

        1. Published metadata
        2. Dynamic connection metadata
        3. Connector creation
        4. Source connection
        5. Schema discovery
        6. Table discovery
        7. Expected source object

    No source or metadata changes are performed.
    """

    print_section("VERIFY POC SOURCE")

    connector: BaseConnector | None = None

    try:
        # -------------------------------------------------------------------
        # STEP 1 - RESOLVE PUBLISHED INGESTION METADATA
        # -------------------------------------------------------------------
        # MetadataResolver reads the published mapping configuration and
        # resolves the complete source/target execution metadata.
        #
        # This proves that the ingestion platform knows WHICH source
        # object the published mapping expects.
        resolver = MetadataResolver()

        execution_metadata = resolver.resolve(
            POC_MAPPING_VERSION_ID
        )

        source_metadata = execution_metadata.source

        print_subsection("PUBLISHED SOURCE METADATA")

        print(
            f"Source ID : "
            f"{source_metadata.source_id}"
        )

        print(
            f"Database  : "
            f"{source_metadata.database_name}"
        )

        print(
            f"Schema    : "
            f"{source_metadata.schema_name}"
        )

        print(
            f"Object    : "
            f"{source_metadata.object_name}"
        )

        # -------------------------------------------------------------------
        # STEP 2 - RESOLVE DYNAMIC CONNECTION
        # -------------------------------------------------------------------
        # ConnectionService reads conn.connection_profile and related
        # metadata to determine how the application should connect to
        # the physical source database.
        #
        # IMPORTANT:
        #
        # We deliberately do NOT print the password/secret.
        #
        # The credential_id is only a reference to the credential metadata.
        # The actual secret is resolved internally by CredentialResolver.
        connection_service = ConnectionService()

        connection_metadata = (
            connection_service.get_connection_metadata(
                source_metadata.connection_id
            )
        )

        print_subsection("DYNAMIC SOURCE CONNECTION")

        print(
            f"Connection ID : "
            f"{connection_metadata.connection_id}"
        )

        print(
            f"Connection    : "
            f"{connection_metadata.connection_name}"
        )

        print(
            f"Connector     : "
            f"{connection_metadata.connector_code}"
        )

        print(
            f"Host          : "
            f"{connection_metadata.host_name}"
        )

        print(
            f"Port          : "
            f"{connection_metadata.port_no}"
        )

        print(
            f"Database      : "
            f"{connection_metadata.database_name}"
        )

        print(
            f"Credential ID : "
            f"{connection_metadata.credential_id}"
        )

        # -------------------------------------------------------------------
        # STEP 3 - CREATE CONNECTOR REGISTRY
        # -------------------------------------------------------------------
        # The registry maps a metadata connector code to a Python connector
        # implementation.
        #
        # Example:
        #
        #     POSTGRESQL_CONNECTOR
        #             |
        #             v
        #     PostgreSQLConnector
        #
        # This avoids hardcoding a PostgreSQL connection directly into
        # the ingestion engine.
        registry = create_registry()

        print_subsection("CONNECTOR REGISTRY")

        print(
            f"Supported Connectors : "
            f"{registry.supported_connectors()}"
        )

        # -------------------------------------------------------------------
        # STEP 4 - CREATE CONNECTOR THROUGH FACTORY
        # -------------------------------------------------------------------
        # ConnectorFactory selects the correct implementation based on
        # connection_metadata.connector_code.
        #
        # This is the point where the platform moves from metadata
        # to an executable connector object.
        factory = ConnectorFactory(registry)

        connector = factory.create(
            connection_metadata
        )

        print(
            f"Selected Connector    : "
            f"{type(connector).__name__}"
        )

        # -------------------------------------------------------------------
        # STEP 5 - TEST SOURCE DATABASE CONNECTION
        # -------------------------------------------------------------------
        # This performs an actual connection test against the physical
        # source database.
        #
        # The connector internally resolves the credential reference
        # and establishes the PostgreSQL connection.
        print_subsection("SOURCE CONNECTION TEST")

        connection_successful = connector.test_connection()

        if not connection_successful:
            raise RuntimeError(
                "Dynamic source connection test failed."
            )

        print(
            "Source database connection successful!"
        )

        # -------------------------------------------------------------------
        # STEP 6 - DISCOVER SOURCE SCHEMAS
        # -------------------------------------------------------------------
        # The metadata says the expected source schema is:
        #
        #     public
        #
        # We now ask the dynamically selected connector to discover
        # the schemas that physically exist in the source database.
        print_subsection("SOURCE SCHEMA DISCOVERY")

        schemas = connector.list_schemas()

        if not schemas:
            raise RuntimeError(
                "No schemas were discovered in the source database."
            )

        print("Discovered Schemas:")

        for schema_name in schemas:
            print(
                f"  {schema_name}"
            )

        expected_schema = source_metadata.schema_name

        if expected_schema not in schemas:
            print()
            print(
                f"WARNING: Expected schema "
                f"'{expected_schema}' was not found."
            )

            print(
                "This indicates that the published metadata and "
                "the dynamically resolved source connection may "
                "refer to different physical databases."
            )

            return

        print()
        print(
            f"Expected schema '{expected_schema}' found."
        )

        # -------------------------------------------------------------------
        # STEP 7 - DISCOVER SOURCE TABLES
        # -------------------------------------------------------------------
        # Once the expected schema exists, discover the tables inside
        # that schema.
        #
        # This proves that the connector can move from:
        #
        #     Database
        #          |
        #          v
        #       Schema
        #          |
        #          v
        #        Tables
        print_subsection(
            f"TABLE DISCOVERY - SCHEMA: {expected_schema}"
        )

        tables = connector.list_tables(
            expected_schema
        )

        if not tables:
            print(
                "No tables were discovered in the expected schema."
            )

            return

        print("Discovered Tables:")

        for table_name in tables:
            print(
                f"  {table_name}"
            )

        expected_object = source_metadata.object_name

        # -------------------------------------------------------------------
        # STEP 8 - VERIFY EXPECTED SOURCE OBJECT
        # -------------------------------------------------------------------
        # The published metadata expects:
        #
        #     public.employee
        #
        # We now verify whether that exact object exists.
        if expected_object not in tables:
            print()
            print(
                f"WARNING: Expected object "
                f"'{expected_object}' was not found."
            )

            print()
            print(
                "Published metadata expects:"
            )

            print(
                f"  {source_metadata.database_name}"
                f".{expected_schema}"
                f".{expected_object}"
            )

            print()
            print(
                "Dynamic connection points to:"
            )

            print(
                f"  {connection_metadata.database_name}"
                f".{expected_schema}"
            )

            print()
            print(
                "The physical source database and published "
                "metadata should be reconciled before implementing "
                "the ingestion runtime."
            )

            return

        # -------------------------------------------------------------------
        # STEP 9 - FINAL SUCCESS
        # -------------------------------------------------------------------
        # Reaching this point proves that the metadata-driven source
        # resolution works from the published mapping all the way to
        # the physical source table.
        print()
        print("=" * 80)
        print("POC SOURCE VERIFICATION SUCCESSFUL")
        print("=" * 80)

        print()
        print(
            "Metadata source : "
            f"{source_metadata.database_name}"
            f".{expected_schema}"
            f".{expected_object}"
        )

        print(
            "Dynamic source  : "
            f"{connection_metadata.database_name}"
            f".{expected_schema}"
            f".{expected_object}"
        )

        print()
        print(
            "The published metadata, dynamic connection, connector "
            "factory, schema discovery and table discovery are "
            "working together successfully."
        )

    finally:
        # -------------------------------------------------------------------
        # STEP 10 - CLEANUP
        # -------------------------------------------------------------------
        # The connector may hold a database connection.
        #
        # Closing it in a finally block ensures cleanup happens even
        # if one of the verification steps raises an exception.
        if connector is not None:
            connector.close()


# ---------------------------------------------------------------------------
# PYTHON MODULE ENTRY POINT
# ---------------------------------------------------------------------------
# This allows the script to be executed using:
#
#     python -m scripts.verify_poc_source
#
# Keeping the entry point explicit also prevents main() from executing
# automatically if this module is imported elsewhere.
if __name__ == "__main__":
    main()