"""
Customer Target Datatype Validation
====================================

Purpose
-------
Validate that every datatype captured for the customer source schema
exists in the PostgreSQL native datatype catalogue.

The validation is READ-ONLY.

This script does NOT:
    - create the target table
    - modify catalog metadata
    - create datatype mapping rules
    - create mapping versions
    - execute target DDL

Metadata flow
-------------
catalog.dataset_field
        |
        | native_datatype_id
        v
dtype.native_datatype
        |
        | platform_id
        | native_type_name
        v
PostgreSQL datatype validation

Why this validation exists
--------------------------
The ingestion platform should use metadata as the source of truth.

Therefore, before generating the target schema, we verify that every
source datatype captured during schema discovery is registered in the
dtype.native_datatype catalogue for the PostgreSQL platform.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC configuration
# ---------------------------------------------------------------------------
# These identifiers represent metadata that has already been created during
# the source schema capture process.
#
# SOURCE_SCHEMA_VERSION_ID:
#     The versioned source schema containing the customer table fields.
#
# POSTGRESQL_PLATFORM_ID:
#     The platform ID representing PostgreSQL in the metadata catalogue.
# ---------------------------------------------------------------------------

SOURCE_SCHEMA_VERSION_ID = 6
POSTGRESQL_PLATFORM_ID = 3


# ---------------------------------------------------------------------------
# Read source fields
# ---------------------------------------------------------------------------


def get_source_fields(connection):
    """
    Read all fields from the selected source schema version.

    The source schema version is already captured in catalog metadata,
    so we use catalog.dataset_field rather than querying the physical
    source database again.

    Returns
    -------
    list
        One row for every source field.
    """

    query = """
        SELECT
            field_id,
            ordinal_no,
            field_name,
            native_datatype_id,
            source_datatype_text
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (SOURCE_SCHEMA_VERSION_ID,),
        )

        return cursor.fetchall()


# ---------------------------------------------------------------------------
# Resolve native datatype
# ---------------------------------------------------------------------------


def get_native_datatype(
    connection,
    native_datatype_id: int,
):
    """
    Resolve a native datatype from dtype.native_datatype.

    Important
    ---------
    The actual metadata table uses:

        native_type_name

    rather than:

        datatype_code
        datatype_name

    The platform ID is also validated so that a datatype belonging to
    another database platform is not accidentally selected.
    """

    query = """
        SELECT
            native_datatype_id,
            platform_id,
            database_version_id,
            canonical_datatype_id,
            native_type_name,
            category_code,
            supports_length,
            supports_precision,
            supports_scale,
            min_length,
            max_length,
            min_precision,
            max_precision,
            min_scale,
            max_scale,
            is_unicode,
            is_signed,
            timezone_semantics_code,
            is_lob,
            is_complex,
            status_code
        FROM dtype.native_datatype
        WHERE native_datatype_id = %s
          AND platform_id = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                native_datatype_id,
                POSTGRESQL_PLATFORM_ID,
            ),
        )

        return cursor.fetchone()


# ---------------------------------------------------------------------------
# Main validation
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Validate every datatype used by the captured customer schema.
    """

    print("=" * 72)
    print("CUSTOMER TARGET DATATYPE VALIDATION")
    print("=" * 72)

    print()
    print(f"Schema Version ID      : {SOURCE_SCHEMA_VERSION_ID}")
    print(f"PostgreSQL Platform ID : {POSTGRESQL_PLATFORM_ID}")

    # -----------------------------------------------------------------------
    # Open metadata-store connection.
    #
    # The connection manager handles opening and closing the database
    # connection. This script performs only SELECT operations, so there is
    # no metadata transaction to commit.
    # -----------------------------------------------------------------------

    with get_metastore_connection() as connection:

        # -------------------------------------------------------------------
        # Retrieve source fields from the captured schema version.
        # -------------------------------------------------------------------

        source_fields = get_source_fields(connection)

        if not source_fields:
            raise LookupError(
                "No source fields found for the selected schema version."
            )

        print()
        print("DATATYPE VALIDATION")
        print("-" * 72)

        validation_count = 0

        # -------------------------------------------------------------------
        # Validate each source field independently.
        # -------------------------------------------------------------------

        for field in source_fields:

            (
                field_id,
                ordinal_no,
                field_name,
                native_datatype_id,
                source_datatype_text,
            ) = field

            # ---------------------------------------------------------------
            # Make sure the source field has a datatype reference.
            # ---------------------------------------------------------------

            if native_datatype_id is None:
                raise ValueError(
                    f"Field '{field_name}' does not have a "
                    "native_datatype_id."
                )

            # ---------------------------------------------------------------
            # Resolve the datatype from the metadata catalogue.
            # ---------------------------------------------------------------

            datatype = get_native_datatype(
                connection,
                native_datatype_id,
            )

            if datatype is None:
                raise LookupError(
                    "Datatype metadata not found for source field: "
                    f"field='{field_name}', "
                    f"native_datatype_id={native_datatype_id}, "
                    f"platform_id={POSTGRESQL_PLATFORM_ID}"
                )

            (
                metadata_datatype_id,
                platform_id,
                database_version_id,
                canonical_datatype_id,
                native_type_name,
                category_code,
                supports_length,
                supports_precision,
                supports_scale,
                min_length,
                max_length,
                min_precision,
                max_precision,
                min_scale,
                max_scale,
                is_unicode,
                is_signed,
                timezone_semantics_code,
                is_lob,
                is_complex,
                status_code,
            ) = datatype

            # ---------------------------------------------------------------
            # Validate the platform.
            #
            # This protects the target planning process from accidentally
            # using a datatype definition belonging to another database
            # platform.
            # ---------------------------------------------------------------

            if platform_id != POSTGRESQL_PLATFORM_ID:
                raise ValueError(
                    f"Datatype for field '{field_name}' belongs to "
                    f"unexpected platform ID {platform_id}."
                )

            # ---------------------------------------------------------------
            # Validate the datatype status.
            #
            # Only ACTIVE datatype definitions should participate in
            # target schema generation.
            # ---------------------------------------------------------------

            if status_code != "ACTIVE":
                raise ValueError(
                    f"Datatype '{native_type_name}' for field "
                    f"'{field_name}' is not ACTIVE. "
                    f"Status={status_code}"
                )

            # ---------------------------------------------------------------
            # Display the resolved metadata.
            # ---------------------------------------------------------------

            print(
                f"{ordinal_no}. {field_name}"
            )

            print(
                f"   Source datatype text : "
                f"{source_datatype_text}"
            )

            print(
                f"   Native datatype ID   : "
                f"{native_datatype_id}"
            )

            print(
                f"   Native type name     : "
                f"{native_type_name}"
            )

            print(
                f"   Category             : "
                f"{category_code}"
            )

            print(
                f"   Platform ID          : "
                f"{platform_id}"
            )

            print(
                f"   Database Version ID  : "
                f"{database_version_id}"
            )

            print(
                f"   Canonical Datatype ID: "
                f"{canonical_datatype_id}"
            )

            print(
                f"   Supports Length      : "
                f"{supports_length}"
            )

            print(
                f"   Supports Precision   : "
                f"{supports_precision}"
            )

            print(
                f"   Supports Scale       : "
                f"{supports_scale}"
            )

            print(
                f"   Status               : "
                f"{status_code}"
            )

            print(
                "   Validation           : PASSED"
            )

            print()

            validation_count += 1

    # -----------------------------------------------------------------------
    # Final result
    # -----------------------------------------------------------------------

    print("=" * 72)
    print("DATATYPE VALIDATION COMPLETED")
    print("=" * 72)

    print()
    print(f"Datatypes validated : {validation_count}")
    print("No metadata changes were made.")


# ---------------------------------------------------------------------------
# Python module entry point
# ---------------------------------------------------------------------------
# This allows the script to be executed using:
#
#     python -m scripts.metadata.verify_customer_target_datatypes
#
# rather than requiring a direct file path.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()