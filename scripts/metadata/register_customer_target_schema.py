"""
Customer Target Schema Registration
===================================

Purpose
-------
Register the planned customer target schema in the catalog metadata.

This script creates:

    1. catalog.dataset_schema_version
    2. catalog.dataset_field records

The script does NOT create the physical PostgreSQL table.

Execution flow
--------------
Source Schema
      |
      v
Target Schema Plan
      |
      v
Target Schema Version
      |
      v
Target Dataset Fields
      |
      v
Physical Target DDL
      |
      v
CREATE TABLE

Important
---------
The physical target table will be created only in a later step.

This separation ensures that the metadata control plane is established
before the runtime modifies the physical target database.

Transaction behavior
--------------------
The entire metadata registration is performed in one transaction.

If any step fails:
    - all inserts are rolled back

If every step succeeds:
    - the transaction is committed
"""

from __future__ import annotations

import hashlib

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC metadata identifiers
# ---------------------------------------------------------------------------
# These objects were already created and verified in earlier steps.
# ---------------------------------------------------------------------------

TARGET_DATASET_ID = 8
TARGET_BINDING_ID = 8

TENANT_ID = 1

# The target schema will be the first schema version for this dataset.
TARGET_VERSION_NO = 1

TARGET_SOURCE_CODE = "CUSTOMER_TARGET"
TARGET_CHANGE_TYPE = "CREATE"


# ---------------------------------------------------------------------------
# Source fields used to construct the target schema
# ---------------------------------------------------------------------------
# For the current POC, the target structure is derived from the already
# captured source schema version.
#
# We deliberately read the source metadata rather than hardcoding the
# customer columns into the INSERT statements.
# ---------------------------------------------------------------------------

SOURCE_SCHEMA_VERSION_ID = 6


# ---------------------------------------------------------------------------
# Read source schema fields
# ---------------------------------------------------------------------------


def get_source_fields(connection):
    """
    Read source fields from the captured source schema version.

    These fields become the basis for the initial target schema plan.
    """

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
            is_nullable,
            default_expression,
            is_identity,
            is_generated
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (SOURCE_SCHEMA_VERSION_ID,),
        )

        rows = cursor.fetchall()

    if not rows:
        raise LookupError(
            "No source fields found for schema version "
            f"{SOURCE_SCHEMA_VERSION_ID}."
        )

    return rows


# ---------------------------------------------------------------------------
# Calculate target schema hash
# ---------------------------------------------------------------------------
# The schema hash provides a deterministic fingerprint of the target
# structure.
#
# It is useful later for:
#     - schema change detection
#     - duplicate version detection
#     - idempotent execution
#     - reconciliation
# ---------------------------------------------------------------------------


def calculate_schema_hash(source_fields) -> str:
    """
    Calculate a deterministic SHA-256 hash for the planned target schema.

    The hash includes:
        - ordinal position
        - field name
        - datatype
        - length
        - precision
        - scale
        - nullability
    """

    schema_components: list[str] = []

    for field in source_fields:
        (
            field_id,
            ordinal_no,
            field_name,
            native_datatype_id,
            source_datatype_text,
            length_value,
            precision_value,
            scale_value,
            is_nullable,
            default_expression,
            is_identity,
            is_generated,
        ) = field

        # ---------------------------------------------------------------
        # Normalize each metadata value so that equivalent schemas
        # produce the same hash.
        # ---------------------------------------------------------------

        component = "|".join(
            [
                str(ordinal_no),
                str(field_name).strip().lower(),
                str(native_datatype_id),
                str(source_datatype_text).strip().lower(),
                str(length_value),
                str(precision_value),
                str(scale_value),
                str(bool(is_nullable)),
            ]
        )

        schema_components.append(component)

    # ---------------------------------------------------------------
    # Preserve field order because ordinal position is part of the
    # schema definition.
    # ---------------------------------------------------------------

    canonical_schema = "\n".join(schema_components)

    return hashlib.sha256(
        canonical_schema.encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------------
# Check whether target schema version already exists
# ---------------------------------------------------------------------------


def find_existing_schema_version(connection):
    """
    Check whether the target schema version already exists.

    This prevents accidental duplicate registration when the script is
    executed more than once.
    """

    query = """
        SELECT
            schema_version_id,
            schema_hash,
            is_current
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s
          AND version_no = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TARGET_DATASET_ID,
                TARGET_VERSION_NO,
            ),
        )

        return cursor.fetchone()


# ---------------------------------------------------------------------------
# Register target schema version
# ---------------------------------------------------------------------------


def register_schema_version(
    connection,
    schema_hash: str,
) -> int:
    """
    Insert the target schema version and return its generated ID.

    Notice that schema_version_id is NOT supplied.

    PostgreSQL generates the identity value automatically.
    """

    query = """
        INSERT INTO catalog.dataset_schema_version
        (
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
        VALUES
        (
            %s,
            %s,
            %s,
            NULL,
            %s,
            %s,
            %s,
            %s,
            TRUE
        )
        RETURNING schema_version_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TENANT_ID,
                TARGET_DATASET_ID,
                TARGET_BINDING_ID,
                TARGET_VERSION_NO,
                schema_hash,
                TARGET_SOURCE_CODE,
                TARGET_CHANGE_TYPE,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Target schema version was inserted but no ID was returned."
        )

    return row[0]


# ---------------------------------------------------------------------------
# Register target fields
# ---------------------------------------------------------------------------


def register_target_fields(
    connection,
    schema_version_id: int,
    source_fields,
) -> int:
    """
    Register target fields using the source schema metadata.

    For the current PostgreSQL -> PostgreSQL POC:

        source field name      -> target field name
        source datatype        -> target datatype
        source native ID       -> target native datatype ID
        source nullability     -> target nullability

    No physical database operation occurs here.
    """

    query = """
        INSERT INTO catalog.dataset_field
        (
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
        VALUES
        (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s
        );
    """

    inserted_count = 0

    with connection.cursor() as cursor:

        for field in source_fields:

            (
                field_id,
                ordinal_no,
                field_name,
                native_datatype_id,
                source_datatype_text,
                length_value,
                precision_value,
                scale_value,
                is_nullable,
                default_expression,
                is_identity,
                is_generated,
            ) = field

            # -----------------------------------------------------------
            # For the same-platform POC, preserve the source field name
            # and PostgreSQL native datatype reference.
            # -----------------------------------------------------------

            cursor.execute(
                query,
                (
                    TENANT_ID,
                    schema_version_id,
                    ordinal_no,
                    field_name,
                    field_name.strip().lower(),
                    native_datatype_id,
                    source_datatype_text,
                    length_value,
                    precision_value,
                    scale_value,
                    is_nullable,
                    default_expression,
                    is_identity,
                    is_generated,
                ),
            )

            inserted_count += 1

    return inserted_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Register the target schema metadata in one transaction.
    """

    print("=" * 72)
    print("CUSTOMER TARGET SCHEMA REGISTRATION")
    print("=" * 72)

    print()
    print("TARGET DATASET")
    print("-" * 72)

    print(f"Tenant ID         : {TENANT_ID}")
    print(f"Dataset ID        : {TARGET_DATASET_ID}")
    print(f"Binding ID        : {TARGET_BINDING_ID}")
    print(f"Version Number    : {TARGET_VERSION_NO}")
    print(f"Source Code       : {TARGET_SOURCE_CODE}")
    print(f"Change Type       : {TARGET_CHANGE_TYPE}")

    # -----------------------------------------------------------------------
    # Open metadata connection.
    #
    # The connection manager does not auto-commit.
    # Therefore this function explicitly controls the transaction.
    # -----------------------------------------------------------------------

    with get_metastore_connection() as connection:

        try:
            # ----------------------------------------------------------------
            # Read source fields.
            # ----------------------------------------------------------------

            source_fields = get_source_fields(connection)

            print()
            print("SOURCE FIELDS")
            print("-" * 72)

            for field in source_fields:

                (
                    field_id,
                    ordinal_no,
                    field_name,
                    native_datatype_id,
                    source_datatype_text,
                    length_value,
                    precision_value,
                    scale_value,
                    is_nullable,
                    default_expression,
                    is_identity,
                    is_generated,
                ) = field

                print(
                    f"{ordinal_no}. "
                    f"{field_name} | "
                    f"{source_datatype_text} | "
                    f"Nullable={is_nullable}"
                )

            # ----------------------------------------------------------------
            # Calculate deterministic target schema hash.
            # ----------------------------------------------------------------

            schema_hash = calculate_schema_hash(
                source_fields
            )

            print()
            print("TARGET SCHEMA HASH")
            print("-" * 72)
            print(f"Schema Hash : {schema_hash}")

            # ----------------------------------------------------------------
            # Check for an existing target schema version.
            # ----------------------------------------------------------------

            existing = find_existing_schema_version(
                connection
            )

            if existing is not None:

                existing_schema_version_id = existing[0]
                existing_hash = existing[1]
                existing_current = existing[2]

                # ------------------------------------------------------------
                # If the same schema already exists, do not insert another
                # copy.
                # ------------------------------------------------------------

                if existing_hash == schema_hash:

                    print()
                    print("TARGET SCHEMA VERSION ALREADY EXISTS")
                    print("-" * 72)

                    print(
                        f"Schema Version ID : "
                        f"{existing_schema_version_id}"
                    )

                    print(
                        f"Schema Hash       : "
                        f"{existing_hash}"
                    )

                    print(
                        f"Current           : "
                        f"{existing_current}"
                    )

                    print()
                    print("No metadata changes were required.")

                    return

                # ------------------------------------------------------------
                # A different schema already exists for version 1.
                # Do not overwrite it automatically.
                # ------------------------------------------------------------

                raise RuntimeError(
                    "Target schema version 1 already exists with a "
                    "different schema hash. Automatic overwrite is "
                    "blocked."
                )

            # ----------------------------------------------------------------
            # Register the target schema version.
            # ----------------------------------------------------------------

            schema_version_id = register_schema_version(
                connection,
                schema_hash,
            )

            print()
            print("TARGET SCHEMA VERSION CREATED")
            print("-" * 72)
            print(
                f"Schema Version ID : "
                f"{schema_version_id}"
            )

            # ----------------------------------------------------------------
            # Register target fields.
            # ----------------------------------------------------------------

            field_count = register_target_fields(
                connection,
                schema_version_id,
                source_fields,
            )

            print(
                f"Target fields     : "
                f"{field_count}"
            )

            # ----------------------------------------------------------------
            # Commit the complete metadata transaction.
            #
            # Both schema version and fields become visible together.
            # ----------------------------------------------------------------

            connection.commit()

            print()
            print("TRANSACTION COMMITTED SUCCESSFULLY")

        except Exception:
            # ----------------------------------------------------------------
            # Roll back everything if any metadata operation fails.
            #
            # This prevents a partially registered target schema.
            # ----------------------------------------------------------------

            connection.rollback()

            print()
            print("TRANSACTION ROLLED BACK")

            raise

    print()
    print("=" * 72)
    print("TARGET SCHEMA REGISTRATION COMPLETED")
    print("=" * 72)


if __name__ == "__main__":
    main()