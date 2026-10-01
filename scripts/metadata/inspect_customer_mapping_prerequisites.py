"""
Customer Mapping Prerequisite Inspection
=========================================

Purpose:
    Validate all metadata required before creating the Customer
    source-to-target mapping.

This script checks:

    1. Customer source dataset and schema version.
    2. Customer source fields.
    3. Customer target dataset and schema version.
    4. Customer target fields.
    5. Available datatype mapping sets.
    6. Existing datatype mapping rules for the source/target types.
    7. Tenant/project ownership of the metadata.

Why:
    We must not guess foreign-key IDs or reuse tenant-specific metadata
    without validating its scope.

Important:
    This script is READ-ONLY.
    No metadata is inserted, updated, or deleted.
"""

# Import the PostgreSQL driver used by the project.
import psycopg

# Import the centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Customer POC metadata identifiers.
#
# These identifiers were already created and verified during the previous
# development steps.
# ---------------------------------------------------------------------------
SOURCE_DATASET_ID = 7
SOURCE_SCHEMA_VERSION_ID = 6

TARGET_DATASET_ID = 8
TARGET_SCHEMA_VERSION_ID = 7

TENANT_ID = 1
PROJECT_ID = 1


def print_section(title: str) -> None:
    """
    Print a standard section header.

    Why:
        Consistent output makes it easier to review the validation results.
    """

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def inspect_dataset(
    connection: psycopg.Connection,
    dataset_id: int,
    expected_role: str,
    label: str,
) -> None:
    """
    Validate a dataset used by the Customer mapping.

    Why:
        The mapping version has foreign keys to catalog.dataset, so the
        dataset must belong to the expected tenant/project and role.
    """

    print_section(f"{label} DATASET")

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
        WHERE dataset_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (dataset_id,))
        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"{label} dataset {dataset_id} was not found."
        )

    (
        actual_dataset_id,
        tenant_id,
        project_id,
        dataset_code,
        dataset_name,
        object_type_code,
        dataset_role_code,
        layer_code,
        status_code,
    ) = row

    print(f"Dataset ID       : {actual_dataset_id}")
    print(f"Tenant ID        : {tenant_id}")
    print(f"Project ID       : {project_id}")
    print(f"Dataset Code     : {dataset_code}")
    print(f"Dataset Name     : {dataset_name}")
    print(f"Object Type      : {object_type_code}")
    print(f"Dataset Role     : {dataset_role_code}")
    print(f"Layer            : {layer_code}")
    print(f"Status           : {status_code}")

    # Validate the expected tenant.
    if tenant_id != TENANT_ID:
        raise ValueError(
            f"{label} dataset belongs to tenant {tenant_id}, "
            f"expected tenant {TENANT_ID}."
        )

    # Validate the expected project.
    if project_id != PROJECT_ID:
        raise ValueError(
            f"{label} dataset belongs to project {project_id}, "
            f"expected project {PROJECT_ID}."
        )

    # Validate SOURCE/TARGET role.
    if dataset_role_code != expected_role:
        raise ValueError(
            f"{label} dataset role is {dataset_role_code}, "
            f"expected {expected_role}."
        )

    print(f"{label} dataset validation: PASSED")


def inspect_schema_version(
    connection: psycopg.Connection,
    schema_version_id: int,
    expected_dataset_id: int,
    label: str,
) -> None:
    """
    Validate a schema version and its relationship to the dataset.

    Why:
        Mapping versions reference immutable source and target schema
        versions. We must ensure the correct versions are being mapped.
    """

    print_section(f"{label} SCHEMA VERSION")

    query = """
        SELECT
            schema_version_id,
            tenant_id,
            dataset_id,
            source_binding_id,
            version_no,
            schema_hash,
            source_code,
            change_type_code,
            is_current
        FROM catalog.dataset_schema_version
        WHERE schema_version_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema_version_id,))
        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            f"{label} schema version {schema_version_id} was not found."
        )

    (
        actual_schema_version_id,
        tenant_id,
        dataset_id,
        source_binding_id,
        version_no,
        schema_hash,
        source_code,
        change_type_code,
        is_current,
    ) = row

    print(f"Schema Version ID : {actual_schema_version_id}")
    print(f"Tenant ID         : {tenant_id}")
    print(f"Dataset ID        : {dataset_id}")
    print(f"Binding ID        : {source_binding_id}")
    print(f"Version No        : {version_no}")
    print(f"Schema Hash       : {schema_hash}")
    print(f"Source Code       : {source_code}")
    print(f"Change Type       : {change_type_code}")
    print(f"Current           : {is_current}")

    # Ensure the schema version belongs to the intended dataset.
    if dataset_id != expected_dataset_id:
        raise ValueError(
            f"{label} schema version belongs to dataset {dataset_id}, "
            f"expected dataset {expected_dataset_id}."
        )

    # Ensure tenant consistency.
    if tenant_id != TENANT_ID:
        raise ValueError(
            f"{label} schema version belongs to tenant {tenant_id}, "
            f"expected tenant {TENANT_ID}."
        )

    print(f"{label} schema version validation: PASSED")


def inspect_fields(
    connection: psycopg.Connection,
    schema_version_id: int,
    label: str,
) -> list[tuple]:
    """
    Display all fields for a schema version.

    Returns:
        A list containing field IDs and field metadata.

    Why:
        mapping_field and mapping_field_input use catalog.dataset_field.field_id
        as their foreign-key references.
    """

    print_section(f"{label} FIELDS")

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
            is_identity,
            is_generated
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema_version_id,))
        rows = cursor.fetchall()

    if not rows:
        raise LookupError(
            f"No fields found for schema version {schema_version_id}."
        )

    print(
        "Field ID | Ordinal | Field Name | Native Type ID | "
        "Source Type | Nullable"
    )
    print("-" * 80)

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
            is_identity,
            is_generated,
        ) = row

        print(
            f"{field_id:>8} | "
            f"{ordinal_no:>7} | "
            f"{field_name:<15} | "
            f"{native_datatype_id:>14} | "
            f"{source_datatype_text:<25} | "
            f"{is_nullable}"
        )

    print(f"Fields discovered: {len(rows)}")

    return rows


def inspect_mapping_sets(connection: psycopg.Connection) -> None:
    """
    Inspect available datatype mapping sets.

    Why:
        map.mapping_version.datatype_mapping_set_id is mandatory and has
        a foreign key to dtype.datatype_mapping_set.mapping_set_id.

        We need to determine whether an existing set can safely be reused
        for this Customer POC.
    """

    print_section("DATATYPE MAPPING SETS")

    query = """
        SELECT *
        FROM dtype.datatype_mapping_set
        ORDER BY mapping_set_id
        LIMIT 50;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

        column_names = [
            description.name
            for description in cursor.description
        ]

    if not rows:
        print("No datatype mapping sets found.")
        return

    print(" | ".join(column_names))
    print("-" * 80)

    for row in rows:
        print(" | ".join(str(value) for value in row))


def inspect_mapping_rules(
    connection: psycopg.Connection,
    source_fields: list[tuple],
    target_fields: list[tuple],
) -> None:
    """
    Inspect datatype mapping rules for the Customer field datatype pairs.

    Why:
        The Customer POC uses the same PostgreSQL platform on source and
        target. We expect the native types to be compatible, but we still
        inspect the live rule catalogue before deciding whether a
        datatype_mapping_rule_id is required.

    Important:
        No new datatype rule is created here.
    """

    print_section("DATATYPE MAPPING RULES")

    # Build the source/target native datatype combinations from the
    # discovered metadata rather than hardcoding datatype IDs.
    datatype_pairs = set()

    for source_field in source_fields:
        source_native_datatype_id = source_field[4]

        for target_field in target_fields:
            target_native_datatype_id = target_field[4]

            # Only inspect matching field positions for this simple POC.
            if source_field[1] == target_field[1]:
                datatype_pairs.add(
                    (
                        source_native_datatype_id,
                        target_native_datatype_id,
                    )
                )

    if not datatype_pairs:
        print("No datatype pairs found.")
        return

    query = """
        SELECT *
        FROM dtype.datatype_mapping_rule
        WHERE source_native_datatype_id = %s
          AND target_native_datatype_id = %s
        ORDER BY mapping_rule_id;
    """

    for source_type_id, target_type_id in sorted(datatype_pairs):
        print()
        print(
            f"Source Native Datatype ID : {source_type_id}"
        )
        print(
            f"Target Native Datatype ID : {target_type_id}"
        )

        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    source_type_id,
                    target_type_id,
                ),
            )

            rows = cursor.fetchall()

            column_names = [
                description.name
                for description in cursor.description
            ]

        if not rows:
            print("No explicit mapping rule found.")
            continue

        print(" | ".join(column_names))
        print("-" * 80)

        for row in rows:
            print(" | ".join(str(value) for value in row))


def main() -> None:
    """
    Run the complete Customer mapping prerequisite validation.

    Why:
        This gives us the exact foreign-key IDs and datatype mapping
        information needed to safely create the mapping.
    """

    print("=" * 80)
    print("CUSTOMER MAPPING PREREQUISITE INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:

        # Validate the source and target dataset identities.
        inspect_dataset(
            connection,
            SOURCE_DATASET_ID,
            "SOURCE",
            "SOURCE",
        )

        inspect_dataset(
            connection,
            TARGET_DATASET_ID,
            "TARGET",
            "TARGET",
        )

        # Validate the immutable source and target schema versions.
        inspect_schema_version(
            connection,
            SOURCE_SCHEMA_VERSION_ID,
            SOURCE_DATASET_ID,
            "SOURCE",
        )

        inspect_schema_version(
            connection,
            TARGET_SCHEMA_VERSION_ID,
            TARGET_DATASET_ID,
            "TARGET",
        )

        # Retrieve the exact source and target field IDs.
        source_fields = inspect_fields(
            connection,
            SOURCE_SCHEMA_VERSION_ID,
            "SOURCE",
        )

        target_fields = inspect_fields(
            connection,
            TARGET_SCHEMA_VERSION_ID,
            "TARGET",
        )

        # Inspect the datatype mapping-set catalogue.
        inspect_mapping_sets(connection)

        # Inspect explicit datatype mapping rules for this POC.
        inspect_mapping_rules(
            connection,
            source_fields,
            target_fields,
        )

    print()
    print("=" * 80)
    print("CUSTOMER MAPPING PREREQUISITE INSPECTION COMPLETED")
    print("=" * 80)
    print("No metadata was modified.")


# Run the inspection when executed as a Python module.
if __name__ == "__main__":
    main()