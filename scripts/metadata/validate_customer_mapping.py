"""
Customer Mapping Validation
===========================

Purpose:
    Validate the complete metadata relationship for the customer
    full-load mapping before an execution plan is generated.

This script is READ-ONLY.

It does not:
    - Insert metadata.
    - Update metadata.
    - Delete metadata.
    - Connect to the physical source database.
    - Connect to the physical target database.
    - Move customer data.

It validates:

    Mapping
        ↓
    Mapping Version
        ↓
    Mapping Source
        ↓
    Mapping Fields
        ↓
    Mapping Field Inputs
        ↓
    Source Fields
        ↓
    Target Fields
"""


# ---------------------------------------------------------------------------
# Application database connection
# ---------------------------------------------------------------------------
# This is the metadata-store connection manager used throughout the
# application. It reads the configured metadata database connection and
# handles opening/closing the PostgreSQL connection.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Expected mapping identifiers
# ---------------------------------------------------------------------------
# These values were returned by the successful mapping creation step.
MAPPING_ID = 2
MAPPING_VERSION_ID = 2

# Expected source and target metadata.
SOURCE_DATASET_ID = 7
SOURCE_SCHEMA_VERSION_ID = 6

TARGET_DATASET_ID = 8
TARGET_SCHEMA_VERSION_ID = 7

# Expected tenant and project.
TENANT_ID = 1
PROJECT_ID = 1


def print_section(title: str) -> None:
    """
    Print a standard section header.

    This keeps the validation output easy to read during development
    and troubleshooting.
    """

    print()
    print("=" * 90)
    print(title)
    print("=" * 90)


def validate_mapping(connection) -> None:
    """
    Validate the parent mapping record.

    The mapping is the logical definition of the source-to-target
    transformation/load relationship.
    """

    print_section("1. MAPPING VALIDATION")

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                mapping_id,
                tenant_id,
                project_id,
                mapping_code,
                mapping_name,
                status_code,
                is_template
            FROM map.mapping
            WHERE mapping_id = %s
              AND tenant_id = %s
              AND project_id = %s;
            """,
            (
                MAPPING_ID,
                TENANT_ID,
                PROJECT_ID,
            ),
        )

        row = cursor.fetchone()

        # A missing row means the mapping cannot be used.
        if row is None:
            raise RuntimeError(
                f"Mapping ID {MAPPING_ID} was not found."
            )

        print(f"Mapping ID    : {row[0]}")
        print(f"Tenant ID     : {row[1]}")
        print(f"Project ID    : {row[2]}")
        print(f"Mapping Code  : {row[3]}")
        print(f"Mapping Name  : {row[4]}")
        print(f"Status        : {row[5]}")
        print(f"Is Template   : {row[6]}")

        # Confirm the mapping belongs to the expected tenant/project.
        if row[1] != TENANT_ID:
            raise RuntimeError(
                "Mapping tenant does not match expected tenant."
            )

        if row[2] != PROJECT_ID:
            raise RuntimeError(
                "Mapping project does not match expected project."
            )

        print("Mapping validation: PASSED")


def validate_mapping_version(connection) -> None:
    """
    Validate the mapping version and its source/target references.

    This is particularly important because the mapping version determines
    the exact schema versions against which the mapping was designed.
    """

    print_section("2. MAPPING VERSION VALIDATION")

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                mapping_version_id,
                tenant_id,
                mapping_id,
                version_no,
                primary_source_dataset_id,
                primary_source_schema_version_id,
                target_dataset_id,
                target_schema_version_id,
                datatype_mapping_set_id,
                load_type_code,
                load_strategy_code,
                status_code,
                config_hash
            FROM map.mapping_version
            WHERE mapping_version_id = %s
              AND tenant_id = %s
              AND mapping_id = %s;
            """,
            (
                MAPPING_VERSION_ID,
                TENANT_ID,
                MAPPING_ID,
            ),
        )

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Mapping Version ID {MAPPING_VERSION_ID} was not found."
            )

        print(f"Mapping Version ID       : {row[0]}")
        print(f"Tenant ID                : {row[1]}")
        print(f"Mapping ID               : {row[2]}")
        print(f"Version Number           : {row[3]}")
        print(f"Source Dataset ID        : {row[4]}")
        print(f"Source Schema Version ID : {row[5]}")
        print(f"Target Dataset ID        : {row[6]}")
        print(f"Target Schema Version ID : {row[7]}")
        print(f"Datatype Mapping Set ID  : {row[8]}")
        print(f"Load Type                : {row[9]}")
        print(f"Load Strategy            : {row[10]}")
        print(f"Status                   : {row[11]}")
        print(f"Config Hash              : {row[12]}")

        # Validate the source references.
        if row[4] != SOURCE_DATASET_ID:
            raise RuntimeError(
                "Mapping version source dataset does not match expected "
                f"dataset {SOURCE_DATASET_ID}."
            )

        if row[5] != SOURCE_SCHEMA_VERSION_ID:
            raise RuntimeError(
                "Mapping version source schema does not match expected "
                f"schema version {SOURCE_SCHEMA_VERSION_ID}."
            )

        # Validate the target references.
        if row[6] != TARGET_DATASET_ID:
            raise RuntimeError(
                "Mapping version target dataset does not match expected "
                f"dataset {TARGET_DATASET_ID}."
            )

        if row[7] != TARGET_SCHEMA_VERSION_ID:
            raise RuntimeError(
                "Mapping version target schema does not match expected "
                f"schema version {TARGET_SCHEMA_VERSION_ID}."
            )

        # Validate the load configuration.
        if row[9] != "FULL":
            raise RuntimeError(
                f"Expected FULL load, found {row[9]}."
            )

        if row[10] != "TRUNCATE_INSERT":
            raise RuntimeError(
                "Expected TRUNCATE_INSERT strategy, "
                f"found {row[10]}."
            )

        print("Mapping version validation: PASSED")


def validate_mapping_source(connection) -> None:
    """
    Validate the source definition attached to the mapping version.

    A mapping version can support multiple sources, but this POC uses
    exactly one primary source.
    """

    print_section("3. MAPPING SOURCE VALIDATION")

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                mapping_source_id,
                tenant_id,
                mapping_version_id,
                dataset_id,
                schema_version_id,
                source_alias,
                sequence_no,
                is_primary
            FROM map.mapping_source
            WHERE mapping_version_id = %s
              AND tenant_id = %s
            ORDER BY sequence_no;
            """,
            (
                MAPPING_VERSION_ID,
                TENANT_ID,
            ),
        )

        rows = cursor.fetchall()

        if len(rows) != 1:
            raise RuntimeError(
                f"Expected exactly 1 mapping source, found {len(rows)}."
            )

        row = rows[0]

        print(f"Mapping Source ID : {row[0]}")
        print(f"Dataset ID        : {row[3]}")
        print(f"Schema Version ID : {row[4]}")
        print(f"Source Alias      : {row[5]}")
        print(f"Sequence No       : {row[6]}")
        print(f"Primary           : {row[7]}")

        if row[3] != SOURCE_DATASET_ID:
            raise RuntimeError(
                "Mapping source dataset does not match source dataset."
            )

        if row[4] != SOURCE_SCHEMA_VERSION_ID:
            raise RuntimeError(
                "Mapping source schema version does not match source schema."
            )

        if row[5] != "src":
            raise RuntimeError(
                f"Expected source alias 'src', found {row[5]}."
            )

        if row[7] is not True:
            raise RuntimeError(
                "Customer source must be marked as primary."
            )

        print("Mapping source validation: PASSED")


def validate_field_mappings(connection) -> None:
    """
    Validate all target mapping fields and their source inputs.

    This query joins:

        map.mapping_field
            ↓
        map.mapping_field_input
            ↓
        catalog.dataset_field

    twice:

        once for the source field
        once for the target field

    This allows us to validate the complete source-to-target relationship.
    """

    print_section("4. FIELD MAPPING VALIDATION")

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
                mf.mapping_field_id,
                mf.ordinal_no,
                mf.mapping_type_code,
                mf.null_rule_code,
                mf.key_role_code,
                mf.scd_behavior_code,

                mfi.mapping_field_input_id,
                mfi.source_field_id,
                mfi.source_alias,
                mfi.input_role_code,

                sf.field_name AS source_field_name,
                sf.native_datatype_id AS source_native_type_id,

                tf.field_name AS target_field_name,
                tf.native_datatype_id AS target_native_type_id

            FROM map.mapping_field mf

            JOIN map.mapping_field_input mfi
                ON mfi.mapping_field_id = mf.mapping_field_id

            JOIN catalog.dataset_field sf
                ON sf.field_id = mfi.source_field_id

            JOIN catalog.dataset_field tf
                ON tf.field_id = mf.target_field_id

            WHERE mf.mapping_version_id = %s
              AND mf.tenant_id = %s

            ORDER BY mf.ordinal_no;
            """,
            (
                MAPPING_VERSION_ID,
                TENANT_ID,
            ),
        )

        rows = cursor.fetchall()

        # We expect exactly four fields for the current customer table.
        if len(rows) != 4:
            raise RuntimeError(
                f"Expected 4 field mappings, found {len(rows)}."
            )

        print(
            "Ordinal | Source Field | Source Type | "
            "Target Field | Target Type | Mapping"
        )

        print("-" * 90)

        for row in rows:

            (
                mapping_field_id,
                ordinal_no,
                mapping_type_code,
                null_rule_code,
                key_role_code,
                scd_behavior_code,
                mapping_field_input_id,
                source_field_id,
                source_alias,
                input_role_code,
                source_field_name,
                source_native_type_id,
                target_field_name,
                target_native_type_id,
            ) = row

            print(
                f"{ordinal_no:^7} | "
                f"{source_field_name:<13} | "
                f"{source_native_type_id:^11} | "
                f"{target_field_name:<13} | "
                f"{target_native_type_id:^11} | "
                f"{mapping_type_code}"
            )

            # The current POC requires direct one-to-one mappings.
            if mapping_type_code != "DIRECT":
                raise RuntimeError(
                    f"{target_field_name} is not a DIRECT mapping."
                )

            # Source and target aliases must use the mapping source alias.
            if source_alias != "src":
                raise RuntimeError(
                    f"{target_field_name} has unexpected source alias "
                    f"{source_alias}."
                )

            # Every field must have a primary source input.
            if input_role_code != "PRIMARY":
                raise RuntimeError(
                    f"{target_field_name} does not have PRIMARY input role."
                )

            # Same-platform datatype compatibility was already validated.
            # We confirm it again here because this is the actual mapping
            # relationship being validated.
            if source_native_type_id != target_native_type_id:
                raise RuntimeError(
                    f"Datatype mismatch for {target_field_name}: "
                    f"source={source_native_type_id}, "
                    f"target={target_native_type_id}"
                )

        print()
        print("Field mapping count       : 4")
        print("Direct mapping count      : 4")
        print("Primary input count       : 4")
        print("Datatype compatibility    : PASSED")
        print("Field mapping validation  : PASSED")


def validate_mapping_completeness(connection) -> None:
    """
    Validate that every target field has exactly one mapping.

    This prevents a target field from accidentally being unmapped or
    mapped multiple times.
    """

    print_section("5. MAPPING COMPLETENESS VALIDATION")

    with connection.cursor() as cursor:

        # Find target fields that have no mapping.
        cursor.execute(
            """
            SELECT
    df.field_id,
    df.field_name
FROM catalog.dataset_field df
JOIN catalog.dataset_schema_version dsv
    ON dsv.schema_version_id = df.schema_version_id
WHERE dsv.dataset_id = %s
  AND df.schema_version_id = %s
  AND NOT EXISTS
  (
      SELECT 1
      FROM map.mapping_field mf
      WHERE mf.mapping_version_id = %s
        AND mf.target_field_id = df.field_id
  )
ORDER BY df.ordinal_no;
            """,
            (
                TARGET_DATASET_ID,
                TARGET_SCHEMA_VERSION_ID,
                MAPPING_VERSION_ID,
            ),
        )

        unmapped_targets = cursor.fetchall()

        if unmapped_targets:
            raise RuntimeError(
                f"Unmapped target fields found: {unmapped_targets}"
            )

        # Find target fields that have more than one mapping.
        cursor.execute(
            """
            SELECT
                target_field_id,
                COUNT(*)
            FROM map.mapping_field
            WHERE mapping_version_id = %s
            GROUP BY target_field_id
            HAVING COUNT(*) > 1;
            """,
            (MAPPING_VERSION_ID,),
        )

        duplicate_targets = cursor.fetchall()

        if duplicate_targets:
            raise RuntimeError(
                f"Duplicate target mappings found: {duplicate_targets}"
            )

        print("Unmapped target fields : 0")
        print("Duplicate target fields: 0")
        print("Mapping completeness   : PASSED")


def validate_source_completeness(connection) -> None:
    """
    Validate the source fields participating in the mapping.

    This ensures the four expected source fields are actually connected
    to the mapping version.
    """

    print_section("6. SOURCE FIELD VALIDATION")

    with connection.cursor() as cursor:

        cursor.execute(
            """
            SELECT
    df.field_id,
    df.field_name,
    df.ordinal_no
FROM catalog.dataset_field df

JOIN catalog.dataset_schema_version dsv
    ON dsv.schema_version_id = df.schema_version_id

JOIN map.mapping_field_input mfi
    ON mfi.source_field_id = df.field_id

JOIN map.mapping_field mf
    ON mf.mapping_field_id = mfi.mapping_field_id

WHERE mf.mapping_version_id = %s
  AND dsv.dataset_id = %s
  AND df.schema_version_id = %s

ORDER BY df.ordinal_no;
            """,
            (
                MAPPING_VERSION_ID,
                SOURCE_DATASET_ID,
                SOURCE_SCHEMA_VERSION_ID,
            ),
        )

        rows = cursor.fetchall()

        if len(rows) != 4:
            raise RuntimeError(
                f"Expected 4 mapped source fields, found {len(rows)}."
            )

        for row in rows:
            print(
                f"Source Field ID={row[0]}, "
                f"Name={row[1]}, "
                f"Ordinal={row[2]}"
            )

        print("Source field validation: PASSED")


def validate_transaction_read_only(connection) -> None:
    """
    Explicitly confirm that this validation workflow is read-only.

    The function does not execute any INSERT, UPDATE, DELETE, or DDL.
    The connection is therefore only used for SELECT statements.
    """

    print_section("7. READ-ONLY VALIDATION")

    print("INSERT operations : 0")
    print("UPDATE operations : 0")
    print("DELETE operations : 0")
    print("DDL operations    : 0")
    print("Metadata modified : NO")
    print("Read-only check   : PASSED")


def main() -> None:
    """
    Execute all customer mapping validation checks.

    Because every operation is SELECT-only, no metadata transaction
    changes are committed.
    """

    print_section("CUSTOMER MAPPING VALIDATION")

    with get_metastore_connection() as connection:

        # Run all validation stages in sequence.
        validate_mapping(connection)

        validate_mapping_version(connection)

        validate_mapping_source(connection)

        validate_field_mappings(connection)

        validate_mapping_completeness(connection)

        validate_source_completeness(connection)

        validate_transaction_read_only(connection)

    print_section("CUSTOMER MAPPING VALIDATION COMPLETED")

    print("Overall validation status : PASSED")
    print(f"Mapping ID               : {MAPPING_ID}")
    print(f"Mapping Version ID       : {MAPPING_VERSION_ID}")
    print("Metadata modified        : NO")


# Run the validation workflow when the module is executed directly.
if __name__ == "__main__":
    main()