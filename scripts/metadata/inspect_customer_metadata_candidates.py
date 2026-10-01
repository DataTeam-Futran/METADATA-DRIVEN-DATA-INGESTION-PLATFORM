"""
Customer Metadata Candidate Inspection
======================================

Purpose
-------
Perform a read-only inspection of the production-style metadata required
for the Customer full-load POC.

The intended execution path is:

    Dynamic Source Connection 1
            |
            v
    catalog.dataset
            |
            v
    catalog.dataset_binding
            |
            v
    catalog.dataset_schema_version
            |
            v
    catalog.dataset_field
            |
            +--------------------+
            |                    |
            v                    v
        dtype metadata       map metadata
            |                    |
            +---------+----------+
                      |
                      v
              Target Connection 11

This script only INSPECTS metadata.

It does NOT:
    - create metadata
    - update metadata
    - delete metadata
    - create target tables
    - run the ingestion
    - modify legacy ingest.* records

The script intentionally uses the dynamic connection metadata:
    Source Connection ID = 1
    Target Connection ID = 11

Secrets are never selected or printed.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC identifiers
# ---------------------------------------------------------------------------
# These IDs were already established during the previous metadata
# investigation. Keeping them as constants makes the inspection repeatable
# and prevents accidental hardcoding of credentials or passwords.
SOURCE_CONNECTION_ID = 1
TARGET_CONNECTION_ID = 11
DATATYPE_MAPPING_SET_ID = 1

# PostgreSQL native datatype IDs already identified in the metadata catalogue.
# INTEGER is used by customer_id.
# CHARACTER VARYING is used by customer_name, email, and city.
POSTGRES_INTEGER_TYPE_ID = 62
POSTGRES_VARCHAR_TYPE_ID = 73


def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    A helper is used so every inspection section has the same readable
    format when the script is executed from PowerShell.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def execute_and_print(
    connection: Any,
    title: str,
    query: str,
    parameters: Sequence[Any] | None = None,
) -> list[tuple[Any, ...]]:
    """
    Execute one read-only SQL query and print its results.

    Why this helper exists:
    - Keeps the main() function easy to read.
    - Ensures all inspection queries use the same output format.
    - Keeps SQL parameters separate from SQL text.
    - Prevents accidental use of string interpolation for SQL values.

    Important psycopg detail:
    PostgreSQL parameters use %s.
    Therefore a literal LIKE pattern such as '%customer%' should NOT be
    embedded directly into a parameterized SQL string. Instead, the pattern
    is passed through the parameters tuple.
    """

    print_section(title)

    with connection.cursor() as cursor:
        # Pass an empty tuple when no parameters are required.
        # This keeps the cursor.execute() call explicit and predictable.
        cursor.execute(
            query,
            parameters if parameters is not None else (),
        )

        rows = cursor.fetchall()

        # Print column names first so the output is self-describing.
        column_names = [
            description.name
            for description in cursor.description
        ]

        print(" | ".join(column_names))
        print("-" * 100)

        if not rows:
            print("No rows returned.")
            return []

        # Print every returned metadata row.
        for row in rows:
            print(" | ".join(str(value) for value in row))

        print()
        print(f"Rows returned: {len(rows)}")

        return rows


def main() -> None:
    """
    Execute the complete Customer metadata candidate inspection.
    """

    print()
    print("=" * 100)
    print("CUSTOMER METADATA CANDIDATE INSPECTION")
    print("=" * 100)

    print(f"Source Connection ID      : {SOURCE_CONNECTION_ID}")
    print(f"Target Connection ID      : {TARGET_CONNECTION_ID}")
    print(f"Datatype Mapping Set ID   : {DATATYPE_MAPPING_SET_ID}")

    # Open the metadata-store connection through the application's standard
    # connection manager. The connection manager does not expose secrets.
    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # 1. Find Customer-related logical datasets
        # -------------------------------------------------------------------
        # We search multiple descriptive fields because the physical object
        # name is stored in catalog.dataset_binding, while the logical
        # dataset identity is stored in catalog.dataset.
        #
        # IMPORTANT:
        # The LIKE patterns are parameters. Do NOT change them to:
        #     LIKE '%customer%'
        # inside the SQL string when using psycopg parameterized execution.
        # Doing so can cause psycopg to interpret %c as a placeholder.
        customer_dataset_rows = execute_and_print(
            connection=connection,
            title="CUSTOMER-RELATED CATALOG DATASETS",
            query="""
                SELECT
                    "dataset_id",
                    "dataset_code",
                    "dataset_name",
                    "object_type_code",
                    "dataset_role_code",
                    "layer_code",
                    "business_name",
                    "status_code"
                FROM catalog.dataset
                WHERE
                    LOWER(COALESCE("dataset_code", '')) LIKE %s
                    OR LOWER(COALESCE("dataset_name", '')) LIKE %s
                    OR LOWER(COALESCE("business_name", '')) LIKE %s
                ORDER BY "dataset_id";
            """,
            parameters=(
                "%customer%",
                "%customer%",
                "%customer%",
            ),
        )

        # -------------------------------------------------------------------
        # 2. Inspect dataset bindings for the physical Customer object
        # -------------------------------------------------------------------
        # catalog.dataset_binding connects a logical dataset to a physical
        # source/target connection and physical database/schema/object.
        #
        # Filtering by the known dynamic source and target connection IDs
        # prevents unrelated bindings from becoming candidates.
        customer_binding_rows = execute_and_print(
            connection=connection,
            title="CUSTOMER DATASET BINDINGS FOR SOURCE/TARGET CONNECTIONS",
            query="""
                SELECT
                    "dataset_binding_id",
                    "dataset_id",
                    "environment_id",
                    "connection_id",
                    "catalog_name",
                    "schema_name",
                    "object_name",
                    "object_name_normalized",
                    "status_code"
                FROM catalog.dataset_binding
                WHERE
                    "connection_id" IN (%s, %s)
                    AND (
                        LOWER(COALESCE("object_name", '')) LIKE %s
                        OR LOWER(COALESCE("object_name_normalized", '')) LIKE %s
                    )
                ORDER BY
                    "connection_id",
                    "dataset_id",
                    "dataset_binding_id";
            """,
            parameters=(
                SOURCE_CONNECTION_ID,
                TARGET_CONNECTION_ID,
                "%customer%",
                "%customer%",
            ),
        )

        # -------------------------------------------------------------------
        # 3. Inspect the authoritative source connection metadata
        # -------------------------------------------------------------------
        # conn.connection_profile is the production-style connection
        # abstraction. It is authoritative for host, port, database,
        # connector version, credential reference, and connection role.
        #
        # Notice that credential_id is selected only as a reference ID.
        # The actual secret is never selected or printed.
        execute_and_print(
            connection=connection,
            title="SOURCE CONNECTION PROFILE",
            query="""
                SELECT
                    "connection_id",
                    "connection_uid",
                    "tenant_id",
                    "system_id",
                    "environment_id",
                    "connector_version_id",
                    "credential_id",
                    "connection_role_code",
                    "connection_name",
                    "host_name",
                    "port_no",
                    "database_name",
                    "connect_timeout_seconds",
                    "command_timeout_seconds",
                    "status_code"
                FROM conn.connection_profile
                WHERE "connection_id" = %s;
            """,
            parameters=(SOURCE_CONNECTION_ID,),
        )

        # -------------------------------------------------------------------
        # 4. Inspect the authoritative target connection metadata
        # -------------------------------------------------------------------
        # Connection 11 is the already-created dynamic target connection.
        # We inspect it instead of creating another target connection.
        execute_and_print(
            connection=connection,
            title="TARGET CONNECTION PROFILE",
            query="""
                SELECT
                    "connection_id",
                    "connection_uid",
                    "tenant_id",
                    "system_id",
                    "environment_id",
                    "connector_version_id",
                    "credential_id",
                    "connection_role_code",
                    "connection_name",
                    "host_name",
                    "port_no",
                    "database_name",
                    "connect_timeout_seconds",
                    "command_timeout_seconds",
                    "status_code"
                FROM conn.connection_profile
                WHERE "connection_id" = %s;
            """,
            parameters=(TARGET_CONNECTION_ID,),
        )

        # -------------------------------------------------------------------
        # 5. Inspect the relevant PostgreSQL native datatype definitions
        # -------------------------------------------------------------------
        # These records tell us which native datatype metadata IDs represent
        # the physical PostgreSQL types discovered from the source.
        #
        # We deliberately inspect exact IDs already established during the
        # previous catalogue investigation rather than guessing datatype IDs.
        execute_and_print(
            connection=connection,
            title="RELEVANT POSTGRESQL NATIVE DATATYPES",
            query="""
                SELECT
                    "native_datatype_id",
                    "platform_id",
                    "database_version_id",
                    "canonical_datatype_id",
                    "native_type_name",
                    "category_code",
                    "supports_length",
                    "supports_precision",
                    "supports_scale",
                    "is_unicode",
                    "is_signed",
                    "is_lob",
                    "is_complex",
                    "status_code"
                FROM dtype.native_datatype
                WHERE "native_datatype_id" IN (%s, %s)
                ORDER BY "native_datatype_id";
            """,
            parameters=(
                POSTGRES_INTEGER_TYPE_ID,
                POSTGRES_VARCHAR_TYPE_ID,
            ),
        )

        # -------------------------------------------------------------------
        # 6. Inspect the datatype mapping-set release
        # -------------------------------------------------------------------
        # A mapping set represents a versioned collection of source-to-target
        # datatype rules. The mapping version later pins the exact set that
        # was used for a load configuration.
        execute_and_print(
            connection=connection,
            title="DATATYPE MAPPING SET",
            query="""
                SELECT
                    "mapping_set_id",
                    "mapping_set_uid",
                    "version_no",
                    "status_code",
                    "effective_from",
                    "effective_to",
                    "source_policy",
                    "config_hash",
                    "approved_at",
                    "published_at"
                FROM dtype.datatype_mapping_set
                WHERE "mapping_set_id" = %s;
            """,
            parameters=(DATATYPE_MAPPING_SET_ID,),
        )

        # -------------------------------------------------------------------
        # 7. Resolve INTEGER -> INTEGER datatype rules
        # -------------------------------------------------------------------
        # Only columns already verified in the actual metadata schema are
        # selected here. Earlier versions assumed columns such as
        # "status_code" existed in dtype.datatype_mapping_rule, but that
        # assumption was incorrect for this database.
        #
        # Keeping the query limited to verified columns makes this inspection
        # resilient to the actual production metadata definition.
        # This checks whether the selected datatype mapping set contains an
        # exact rule from the PostgreSQL INTEGER source type to the same
        # PostgreSQL INTEGER target type.
        #
        # We inspect the rule rather than assuming that source and target
        # native datatype IDs are automatically compatible.
        execute_and_print(
            connection=connection,
            title="INTEGER -> INTEGER DATATYPE RULES",
            query="""
                SELECT
                    "mapping_rule_id",
                    "mapping_set_id",
                    "source_native_datatype_id",
                    "target_native_datatype_id"
                FROM dtype.datatype_mapping_rule
                WHERE
                    "mapping_set_id" = %s
                    AND "source_native_datatype_id" = %s
                    AND "target_native_datatype_id" = %s
                ORDER BY "mapping_rule_id";
            """,
            parameters=(
                DATATYPE_MAPPING_SET_ID,
                POSTGRES_INTEGER_TYPE_ID,
                POSTGRES_INTEGER_TYPE_ID,
            ),
        )

        # -------------------------------------------------------------------
        # 8. Resolve CHARACTER VARYING -> CHARACTER VARYING rules
        # -------------------------------------------------------------------
        # Customer has several character fields, so this verifies that the
        # selected mapping set contains the corresponding exact rule.
        execute_and_print(
            connection=connection,
            title="CHARACTER VARYING -> CHARACTER VARYING DATATYPE RULES",
            query="""
                SELECT
                    "mapping_rule_id",
                    "mapping_set_id",
                    "source_native_datatype_id",
                    "target_native_datatype_id"
                FROM dtype.datatype_mapping_rule
                WHERE
                    "mapping_set_id" = %s
                    AND "source_native_datatype_id" = %s
                    AND "target_native_datatype_id" = %s
                ORDER BY "mapping_rule_id";
            """,
            parameters=(
                DATATYPE_MAPPING_SET_ID,
                POSTGRES_VARCHAR_TYPE_ID,
                POSTGRES_VARCHAR_TYPE_ID,
            ),
        )

        # -------------------------------------------------------------------
        # 9. If Customer datasets were found, inspect their schema versions
        # -------------------------------------------------------------------
        # This section narrows the inspection from the logical dataset to
        # immutable schema versions. A schema version is important because
        # mappings should point to a specific version instead of dynamically
        # changing underneath an active mapping.
        dataset_ids = [
            row[0]
            for row in customer_dataset_rows
            if row and row[0] is not None
        ]

        if dataset_ids:
            execute_and_print(
                connection=connection,
                title="CUSTOMER DATASET SCHEMA VERSIONS",
                query="""
                    SELECT
                        "schema_version_id",
                        "dataset_id",
                        "source_binding_id",
                        "schema_capture_run_id",
                        "version_no",
                        "schema_hash",
                        "source_code",
                        "change_type_code",
                        "captured_at",
                        "is_current",
                        "status_code"
                    FROM catalog.dataset_schema_version
                    WHERE "dataset_id" = ANY(%s)
                    ORDER BY
                        "dataset_id",
                        "version_no",
                        "schema_version_id";
                """,
                parameters=(dataset_ids,),
            )

        # -------------------------------------------------------------------
        # 10. Inspect Customer fields for the discovered schema versions
        # -------------------------------------------------------------------
        # This is the field-level metadata required by the mapping engine.
        # The field records contain source field names and native datatype
        # references. The actual ingestion runtime should use these metadata
        # records rather than hardcoded column definitions.
        if dataset_ids:
            execute_and_print(
                connection=connection,
                title="CUSTOMER DATASET FIELDS",
                query="""
                    SELECT
                        "field_id",
                        "schema_version_id",
                        "ordinal_no",
                        "field_name",
                        "field_name_normalized",
                        "native_datatype_id",
                        "source_datatype_text",
                        "length_value",
                        "precision_value",
                        "scale_value",
                        "is_nullable"
                    FROM catalog.dataset_field
                    WHERE "schema_version_id" IN (
                        SELECT "schema_version_id"
                        FROM catalog.dataset_schema_version
                        WHERE "dataset_id" = ANY(%s)
                    )
                    ORDER BY
                        "schema_version_id",
                        "ordinal_no",
                        "field_id";
                """,
                parameters=(dataset_ids,),
            )

        # -------------------------------------------------------------------
        # 11. Final inspection summary
        # -------------------------------------------------------------------
        # No metadata is changed by this script. The summary simply tells the
        # developer what this inspection has established and what should be
        # inspected next.
        print_section("INSPECTION COMPLETE")

        print("No metadata was modified.")
        print()
        print("Authoritative source connection : 1")
        print("Authoritative target connection : 11")
        print("Datatype mapping set            : 1")
        print()
        print("Next development step:")
        print(
            "Use the returned catalog.dataset, dataset_binding, "
            "dataset_schema_version, dataset_field, and dtype records "
            "to determine whether the Customer source is already fully "
            "represented in the production metadata model."
        )
        print()
        print(
            "Do not create or update mapping metadata until the source "
            "dataset, schema version, fields, target dataset, target "
            "schema version, and datatype rules have been verified."
        )


if __name__ == "__main__":
    # Run the inspection only when this module is executed directly.
    main()
