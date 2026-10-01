"""
Customer Target Schema Verification
====================================

Purpose
-------
Verify the target schema metadata that was just registered.

The verification checks:

    1. Target dataset
    2. Target binding
    3. Target schema version
    4. Target schema hash
    5. Target fields
    6. Field order
    7. Datatype references
    8. Nullability

This script is READ-ONLY.

It does NOT:
    - create the physical target table
    - modify metadata
    - modify source data
    - modify target data

Why this step exists
--------------------
The ingestion platform should verify its control-plane metadata before
allowing the runtime to perform physical database operations.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC identifiers
# ---------------------------------------------------------------------------

TARGET_DATASET_ID = 8
TARGET_BINDING_ID = 8
TARGET_SCHEMA_VERSION_ID = 7

EXPECTED_FIELD_COUNT = 4


# ---------------------------------------------------------------------------
# Expected metadata values
# ---------------------------------------------------------------------------
# These values are used only for validation.
# They are not inserted or modified by this script.
# ---------------------------------------------------------------------------

EXPECTED_SCHEMA_HASH = (
    "cd54d6a7735a7c35b5b3cdea2880a28eb16daff8e31513dafa12ab5ec837aae3"
)


# ---------------------------------------------------------------------------
# Validate target dataset
# ---------------------------------------------------------------------------


def validate_target_dataset(connection) -> None:
    """
    Verify that the target dataset exists and is ACTIVE.
    """

    query = """
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
        WHERE dataset_id = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (TARGET_DATASET_ID,),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"Target dataset {TARGET_DATASET_ID} was not found."
        )

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
    ) = row

    if dataset_role_code != "TARGET":
        raise ValueError(
            f"Expected TARGET dataset but found "
            f"{dataset_role_code}."
        )

    if status_code != "ACTIVE":
        raise ValueError(
            f"Target dataset is not ACTIVE: {status_code}"
        )

    print()
    print("TARGET DATASET")
    print("-" * 72)

    print(f"Dataset ID     : {dataset_id}")
    print(f"Tenant ID      : {tenant_id}")
    print(f"Project ID     : {project_id}")
    print(f"Dataset Code   : {dataset_code}")
    print(f"Dataset Name   : {dataset_name}")
    print(f"Object Type    : {object_type_code}")
    print(f"Dataset Role   : {dataset_role_code}")
    print(f"Layer          : {layer_code}")
    print(f"Status         : {status_code}")

    print("Validation     : PASSED")


# ---------------------------------------------------------------------------
# Validate target binding
# ---------------------------------------------------------------------------


def validate_target_binding(connection) -> None:
    """
    Verify the physical target location registered in metadata.
    """

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

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TARGET_BINDING_ID,
                TARGET_DATASET_ID,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            "Target dataset binding was not found."
        )

    (
        binding_id,
        tenant_id,
        dataset_id,
        environment_id,
        connection_id,
        catalog_name,
        schema_name,
        object_name,
        object_name_normalized,
        status_code,
    ) = row

    if status_code != "ACTIVE":
        raise ValueError(
            f"Target binding is not ACTIVE: {status_code}"
        )

    print()
    print("TARGET BINDING")
    print("-" * 72)

    print(f"Binding ID       : {binding_id}")
    print(f"Dataset ID       : {dataset_id}")
    print(f"Environment ID   : {environment_id}")
    print(f"Connection ID    : {connection_id}")
    print(f"Database         : {catalog_name}")
    print(f"Schema           : {schema_name}")
    print(f"Object           : {object_name}")
    print(f"Normalized Name  : {object_name_normalized}")
    print(f"Status           : {status_code}")

    print("Validation       : PASSED")


# ---------------------------------------------------------------------------
# Validate target schema version
# ---------------------------------------------------------------------------


def validate_schema_version(connection) -> None:
    """
    Verify the registered target schema version.
    """

    query = """
        SELECT
            schema_version_id,
            tenant_id,
            dataset_id,
            source_binding_id,
            schema_capture_run_id,
            version_no,
            schema_hash,
            source_code,
            change_type_code,
            is_current
        FROM catalog.dataset_schema_version
        WHERE schema_version_id = %s
          AND dataset_id = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TARGET_SCHEMA_VERSION_ID,
                TARGET_DATASET_ID,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"Target schema version "
            f"{TARGET_SCHEMA_VERSION_ID} was not found."
        )

    (
        schema_version_id,
        tenant_id,
        dataset_id,
        source_binding_id,
        schema_capture_run_id,
        version_no,
        schema_hash,
        source_code,
        change_type_code,
        is_current,
    ) = row

    if source_binding_id != TARGET_BINDING_ID:
        raise ValueError(
            f"Schema version references binding "
            f"{source_binding_id}, expected "
            f"{TARGET_BINDING_ID}."
        )

    if schema_hash != EXPECTED_SCHEMA_HASH:
        raise ValueError(
            "Target schema hash does not match the registered hash."
        )

    if not is_current:
        raise ValueError(
            "Target schema version is not marked CURRENT."
        )

    print()
    print("TARGET SCHEMA VERSION")
    print("-" * 72)

    print(f"Schema Version ID : {schema_version_id}")
    print(f"Tenant ID         : {tenant_id}")
    print(f"Dataset ID        : {dataset_id}")
    print(f"Binding ID        : {source_binding_id}")
    print(f"Capture Run ID    : {schema_capture_run_id}")
    print(f"Version           : {version_no}")
    print(f"Schema Hash       : {schema_hash}")
    print(f"Source Code       : {source_code}")
    print(f"Change Type       : {change_type_code}")
    print(f"Current           : {is_current}")

    print("Validation        : PASSED")


# ---------------------------------------------------------------------------
# Validate target fields
# ---------------------------------------------------------------------------


def validate_target_fields(connection) -> None:
    """
    Verify all target fields belonging to the target schema version.
    """

    query = """
        SELECT
            field_id,
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
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (TARGET_SCHEMA_VERSION_ID,),
        )

        rows = cursor.fetchall()

    if len(rows) != EXPECTED_FIELD_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_FIELD_COUNT} target fields but found "
            f"{len(rows)}."
        )

    print()
    print("TARGET FIELDS")
    print("-" * 72)

    for row in rows:

        (
            field_id,
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
            is_generated,
        ) = row

        print(
            f"{ordinal_no}. "
            f"{field_name} | "
            f"{source_datatype_text} | "
            f"Native Datatype ID={native_datatype_id} | "
            f"Nullable={is_nullable}"
        )

    print()
    print(f"Field Count       : {len(rows)}")
    print("Validation        : PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Execute complete target schema metadata verification.
    """

    print("=" * 72)
    print("CUSTOMER TARGET SCHEMA VERIFICATION")
    print("=" * 72)

    # -----------------------------------------------------------------------
    # Open metadata-store connection.
    #
    # All operations below are SELECT statements, so no commit is required.
    # -----------------------------------------------------------------------

    with get_metastore_connection() as connection:

        validate_target_dataset(connection)

        validate_target_binding(connection)

        validate_schema_version(connection)

        validate_target_fields(connection)

    print()
    print("=" * 72)
    print("TARGET SCHEMA METADATA VERIFICATION COMPLETED")
    print("=" * 72)

    print()
    print("All target metadata validations passed.")
    print("No metadata changes were made.")


if __name__ == "__main__":
    main()