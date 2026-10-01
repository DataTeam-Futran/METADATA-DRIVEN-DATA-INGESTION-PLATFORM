"""
Create Customer Full-Load Mapping Metadata
===========================================

Purpose:
    Create the metadata required to describe how the CUSTOMER source
    dataset maps into the CUSTOMER_TARGET target dataset.

Metadata created:

    1. map.mapping
    2. map.mapping_version
    3. map.mapping_source
    4. map.mapping_field
    5. map.mapping_field_input

Source:
    Dataset ID       : 7
    Schema Version   : 6

Target:
    Dataset ID       : 8
    Schema Version   : 7

Load configuration:
    Load Type        : FULL
    Load Strategy    : TRUNCATE_INSERT

Important:
    - This script only creates metadata.
    - It does NOT read source data.
    - It does NOT write target data.
    - It does NOT create or modify physical tables.
    - The complete metadata operation is executed in one transaction.
    - If any insert fails, the transaction is rolled back.
"""

# hashlib is used to generate a deterministic SHA-256 configuration hash.
import hashlib

# json is used to create a canonical representation of the mapping
# configuration before generating the hash.
import json

# psycopg provides the PostgreSQL database connection and SQL execution.
import psycopg

# Import the application's standard metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Customer mapping constants
# ---------------------------------------------------------------------------
# These IDs were verified by the prerequisite inspection script.
TENANT_ID = 1
PROJECT_ID = 1

SOURCE_DATASET_ID = 7
SOURCE_SCHEMA_VERSION_ID = 6

TARGET_DATASET_ID = 8
TARGET_SCHEMA_VERSION_ID = 7

# Mapping code must be unique within the tenant/project combination.
MAPPING_CODE = "CUSTOMER_FULL_LOAD_MAPPING"

# Human-readable mapping name.
MAPPING_NAME = "Customer Full Load Mapping"

# The published datatype mapping set discovered during prerequisite inspection.
DATATYPE_MAPPING_SET_ID = 1

# Full-load strategy confirmed by the platform's existing mapping metadata.
LOAD_TYPE_CODE = "FULL"
LOAD_STRATEGY_CODE = "TRUNCATE_INSERT"

# Source alias used by map.mapping_source and map.mapping_field_input.
SOURCE_ALIAS = "src"


# ---------------------------------------------------------------------------
# Source and target field definitions
# ---------------------------------------------------------------------------
# The prerequisite inspection confirmed these exact field IDs.
#
# Notice that the source and target IDs are different because they are
# different catalog.dataset_field records, even though their physical
# field names and native datatype IDs are identical.
FIELD_MAPPINGS = [
    {
        "ordinal": 1,
        "source_field_id": 38,
        "target_field_id": 42,
        "field_name": "customer_id",
    },
    {
        "ordinal": 2,
        "source_field_id": 39,
        "target_field_id": 43,
        "field_name": "customer_name",
    },
    {
        "ordinal": 3,
        "source_field_id": 40,
        "target_field_id": 44,
        "field_name": "email",
    },
    {
        "ordinal": 4,
        "source_field_id": 41,
        "target_field_id": 45,
        "field_name": "city",
    },
]


def print_section(title: str) -> None:
    """
    Print a consistent section header.

    This makes the script output easier to read during development
    and troubleshooting.
    """

    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def generate_config_hash() -> str:
    """
    Generate a deterministic SHA-256 hash for the mapping configuration.

    Why this is used:
        mapping_version.config_hash is intended to represent the exact
        configuration of the mapping version.

        If the mapping configuration changes later, the generated hash
        will also change.

    The JSON is sorted so that the same logical configuration always
    produces the same hash.
    """

    # Build a canonical dictionary containing all configuration that
    # defines this mapping version.
    configuration = {
        "tenant_id": TENANT_ID,
        "project_id": PROJECT_ID,
        "source_dataset_id": SOURCE_DATASET_ID,
        "source_schema_version_id": SOURCE_SCHEMA_VERSION_ID,
        "target_dataset_id": TARGET_DATASET_ID,
        "target_schema_version_id": TARGET_SCHEMA_VERSION_ID,
        "datatype_mapping_set_id": DATATYPE_MAPPING_SET_ID,
        "load_type_code": LOAD_TYPE_CODE,
        "load_strategy_code": LOAD_STRATEGY_CODE,
        "source_alias": SOURCE_ALIAS,
        "field_mappings": FIELD_MAPPINGS,
    }

    # Convert the configuration into deterministic JSON.
    canonical_json = json.dumps(
        configuration,
        sort_keys=True,
        separators=(",", ":"),
    )

    # Generate SHA-256 and return its hexadecimal representation.
    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def validate_prerequisites(connection: psycopg.Connection) -> None:
    """
    Validate that the expected source and target metadata still exists.

    Why this is important:
        IDs such as dataset_id and field_id are metadata references.
        Before inserting mapping records, we verify that they still
        point to the expected metadata.

    This prevents creating a mapping against an unexpected object.
    """

    print_section("VALIDATING MAPPING PREREQUISITES")

    with connection.cursor() as cursor:

        # Validate the source dataset.
        cursor.execute(
            """
            SELECT
                dataset_id,
                tenant_id,
                project_id,
                dataset_code,
                dataset_role_code,
                status_code
            FROM catalog.dataset
            WHERE dataset_id = %s
              AND tenant_id = %s;
            """,
            (SOURCE_DATASET_ID, TENANT_ID),
        )

        source_dataset = cursor.fetchone()

        if source_dataset is None:
            raise RuntimeError(
                f"Source dataset {SOURCE_DATASET_ID} was not found."
            )

        print(
            f"Source dataset validated: "
            f"{source_dataset[3]} "
            f"(ID={source_dataset[0]})"
        )

        # Validate the target dataset.
        cursor.execute(
            """
            SELECT
                dataset_id,
                tenant_id,
                project_id,
                dataset_code,
                dataset_role_code,
                status_code
            FROM catalog.dataset
            WHERE dataset_id = %s
              AND tenant_id = %s;
            """,
            (TARGET_DATASET_ID, TENANT_ID),
        )

        target_dataset = cursor.fetchone()

        if target_dataset is None:
            raise RuntimeError(
                f"Target dataset {TARGET_DATASET_ID} was not found."
            )

        print(
            f"Target dataset validated: "
            f"{target_dataset[3]} "
            f"(ID={target_dataset[0]})"
        )

        # Validate source schema version.
        cursor.execute(
            """
            SELECT
                schema_version_id,
                dataset_id,
                tenant_id,
                version_no,
                is_current
            FROM catalog.dataset_schema_version
            WHERE schema_version_id = %s
              AND dataset_id = %s
              AND tenant_id = %s;
            """,
            (
                SOURCE_SCHEMA_VERSION_ID,
                SOURCE_DATASET_ID,
                TENANT_ID,
            ),
        )

        source_schema = cursor.fetchone()

        if source_schema is None:
            raise RuntimeError(
                f"Source schema version {SOURCE_SCHEMA_VERSION_ID} "
                f"was not found."
            )

        print(
            f"Source schema validated: "
            f"ID={source_schema[0]}, "
            f"version={source_schema[3]}"
        )

        # Validate target schema version.
        cursor.execute(
            """
            SELECT
                schema_version_id,
                dataset_id,
                tenant_id,
                version_no,
                is_current
            FROM catalog.dataset_schema_version
            WHERE schema_version_id = %s
              AND dataset_id = %s
              AND tenant_id = %s;
            """,
            (
                TARGET_SCHEMA_VERSION_ID,
                TARGET_DATASET_ID,
                TENANT_ID,
            ),
        )

        target_schema = cursor.fetchone()

        if target_schema is None:
            raise RuntimeError(
                f"Target schema version {TARGET_SCHEMA_VERSION_ID} "
                f"was not found."
            )

        print(
            f"Target schema validated: "
            f"ID={target_schema[0]}, "
            f"version={target_schema[3]}"
        )


def check_existing_mapping(
    connection: psycopg.Connection,
) -> None:
    """
    Check whether the customer mapping already exists.

    Why:
        The mapping code is unique within tenant + project.

        Instead of accidentally creating duplicate metadata or getting
        an unclear database error, fail early with a useful message.
    """

    print_section("CHECKING FOR EXISTING MAPPING")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                mapping_id,
                mapping_code,
                status_code
            FROM map.mapping
            WHERE tenant_id = %s
              AND project_id = %s
              AND mapping_code = %s;
            """,
            (
                TENANT_ID,
                PROJECT_ID,
                MAPPING_CODE,
            ),
        )

        existing_mapping = cursor.fetchone()

        if existing_mapping is not None:
            raise RuntimeError(
                "Customer mapping already exists: "
                f"mapping_id={existing_mapping[0]}, "
                f"mapping_code={existing_mapping[1]}, "
                f"status={existing_mapping[2]}"
            )

        print("No existing customer mapping found.")
        print("Safe to create new mapping metadata.")


def create_mapping(
    connection: psycopg.Connection,
) -> tuple[int, int]:
    """
    Create the parent mapping and mapping version.

    Returns:
        mapping_id
        mapping_version_id
    """

    print_section("CREATING MAPPING")

    config_hash = generate_config_hash()

    print(f"Mapping Code : {MAPPING_CODE}")
    print(f"Load Type    : {LOAD_TYPE_CODE}")
    print(f"Load Strategy: {LOAD_STRATEGY_CODE}")
    print(f"Config Hash  : {config_hash}")

    with connection.cursor() as cursor:

        # Create the logical mapping definition.
        #
        # We use DRAFT because the mapping has not yet passed all
        # downstream validation and execution gates.
        cursor.execute(
            """
            INSERT INTO map.mapping
            (
                tenant_id,
                project_id,
                mapping_code,
                mapping_name,
                business_purpose,
                is_template,
                status_code
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING mapping_id;
            """,
            (
                TENANT_ID,
                PROJECT_ID,
                MAPPING_CODE,
                MAPPING_NAME,
                "Full load mapping from customer source table "
                "to customer target table.",
                False,
                "DRAFT",
            ),
        )

        mapping_id = cursor.fetchone()[0]

        # Create version 1 of the mapping.
        #
        # The version references the exact source and target schema
        # versions discovered earlier.
        cursor.execute(
            """
            INSERT INTO map.mapping_version
            (
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
                %s
            )
            RETURNING mapping_version_id;
            """,
            (
                TENANT_ID,
                mapping_id,
                1,
                SOURCE_DATASET_ID,
                SOURCE_SCHEMA_VERSION_ID,
                TARGET_DATASET_ID,
                TARGET_SCHEMA_VERSION_ID,
                DATATYPE_MAPPING_SET_ID,
                LOAD_TYPE_CODE,
                LOAD_STRATEGY_CODE,
                "DRAFT",
                config_hash,
            ),
        )

        mapping_version_id = cursor.fetchone()[0]

    print(f"Mapping ID         : {mapping_id}")
    print(f"Mapping Version ID : {mapping_version_id}")

    return mapping_id, mapping_version_id


def create_mapping_source(
    connection: psycopg.Connection,
    mapping_version_id: int,
) -> int:
    """
    Create the source dataset reference for the mapping version.

    The source is given the alias 'src', which will later allow
    transformation expressions and generated SQL to refer to the
    source consistently.
    """

    print_section("CREATING MAPPING SOURCE")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO map.mapping_source
            (
                tenant_id,
                mapping_version_id,
                dataset_id,
                schema_version_id,
                source_alias,
                sequence_no,
                is_primary
            )
            VALUES
            (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s
            )
            RETURNING mapping_source_id;
            """,
            (
                TENANT_ID,
                mapping_version_id,
                SOURCE_DATASET_ID,
                SOURCE_SCHEMA_VERSION_ID,
                SOURCE_ALIAS,
                1,
                True,
            ),
        )

        mapping_source_id = cursor.fetchone()[0]

    print(f"Mapping Source ID : {mapping_source_id}")

    return mapping_source_id


def create_mapping_fields(
    connection: psycopg.Connection,
    mapping_version_id: int,
) -> list[tuple[int, int]]:
    """
    Create target mapping fields and their source inputs.

    Returns:
        A list containing:
            (mapping_field_id, source_field_id)

    Why:
        map.mapping_field describes the target-side mapping.

        map.mapping_field_input connects that target mapping field
        to its source field.
    """

    print_section("CREATING MAPPING FIELDS")

    created_fields: list[tuple[int, int]] = []

    with connection.cursor() as cursor:

        for field_mapping in FIELD_MAPPINGS:

            # ---------------------------------------------------------------
            # Create target-side mapping field.
            # ---------------------------------------------------------------
            #
            # DIRECT means the target field receives the source field
            # value without an expression or lookup.
            #
            # datatype_mapping_rule_id is intentionally NULL because
            # prerequisite inspection confirmed that source and target
            # native datatype IDs are identical.
            #
            cursor.execute(
                """
                INSERT INTO map.mapping_field
                (
                    tenant_id,
                    mapping_version_id,
                    target_field_id,
                    mapping_type_code,
                    transform_function_id,
                    lookup_id,
                    datatype_mapping_rule_id,
                    transform_expression,
                    expression_language_code,
                    null_rule_code,
                    default_value,
                    format_mask,
                    key_role_code,
                    scd_behavior_code,
                    ordinal_no
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    NULL,
                    %s,
                    NULL,
                    NULL,
                    %s,
                    %s,
                    %s
                )
                RETURNING mapping_field_id;
                """,
                (
                    TENANT_ID,
                    mapping_version_id,
                    field_mapping["target_field_id"],
                    "DIRECT",
                    "KEEP",
                    "NONE",
                    "NA",
                    field_mapping["ordinal"],
                ),
            )

            mapping_field_id = cursor.fetchone()[0]

            # ---------------------------------------------------------------
            # Create the source input for the mapping field.
            # ---------------------------------------------------------------
            #
            # Each target field has exactly one source input in this
            # direct one-to-one mapping.
            #
            cursor.execute(
                """
                INSERT INTO map.mapping_field_input
                (
                    tenant_id,
                    mapping_field_id,
                    source_field_id,
                    source_alias,
                    input_role_code,
                    ordinal_no
                )
                VALUES
                (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                RETURNING mapping_field_input_id;
                """,
                (
                    TENANT_ID,
                    mapping_field_id,
                    field_mapping["source_field_id"],
                    SOURCE_ALIAS,
                    "PRIMARY",
                    1,
                ),
            )

            mapping_field_input_id = cursor.fetchone()[0]

            created_fields.append(
                (
                    mapping_field_id,
                    field_mapping["source_field_id"],
                )
            )

            print(
                f"{field_mapping['field_name']:<20} "
                f"Source Field ID={field_mapping['source_field_id']:<4} "
                f"Target Field ID={field_mapping['target_field_id']:<4} "
                f"Mapping Field ID={mapping_field_id:<4} "
                f"Input ID={mapping_field_input_id}"
            )

    return created_fields


def verify_mapping(
    connection: psycopg.Connection,
    mapping_id: int,
    mapping_version_id: int,
) -> None:
    """
    Verify the metadata created by this transaction.

    The verification checks:
        - Mapping exists.
        - Mapping version exists.
        - Exactly one source exists.
        - Exactly four mapping fields exist.
        - Exactly four mapping inputs exist.
        - All mappings are DIRECT.
    """

    print_section("VERIFYING CREATED MAPPING")

    with connection.cursor() as cursor:

        # Verify mapping.
        cursor.execute(
            """
            SELECT
                mapping_id,
                mapping_code,
                status_code
            FROM map.mapping
            WHERE mapping_id = %s;
            """,
            (mapping_id,),
        )

        mapping = cursor.fetchone()

        if mapping is None:
            raise RuntimeError("Created mapping could not be verified.")

        print(
            f"Mapping verified: "
            f"ID={mapping[0]}, "
            f"Code={mapping[1]}, "
            f"Status={mapping[2]}"
        )

        # Verify mapping version.
        cursor.execute(
            """
            SELECT
                mapping_version_id,
                version_no,
                primary_source_dataset_id,
                target_dataset_id,
                datatype_mapping_set_id,
                load_type_code,
                load_strategy_code,
                status_code
            FROM map.mapping_version
            WHERE mapping_version_id = %s;
            """,
            (mapping_version_id,),
        )

        version = cursor.fetchone()

        if version is None:
            raise RuntimeError(
                "Created mapping version could not be verified."
            )

        print(
            f"Mapping Version verified: "
            f"ID={version[0]}, "
            f"Version={version[1]}, "
            f"Source Dataset={version[2]}, "
            f"Target Dataset={version[3]}, "
            f"Datatype Set={version[4]}, "
            f"Load Type={version[5]}, "
            f"Strategy={version[6]}, "
            f"Status={version[7]}"
        )

        # Verify mapping source count.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM map.mapping_source
            WHERE mapping_version_id = %s;
            """,
            (mapping_version_id,),
        )

        source_count = cursor.fetchone()[0]

        if source_count != 1:
            raise RuntimeError(
                f"Expected 1 mapping source, found {source_count}."
            )

        print("Mapping source count: 1")

        # Verify mapping field count.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM map.mapping_field
            WHERE mapping_version_id = %s;
            """,
            (mapping_version_id,),
        )

        field_count = cursor.fetchone()[0]

        if field_count != 4:
            raise RuntimeError(
                f"Expected 4 mapping fields, found {field_count}."
            )

        print("Mapping field count: 4")

        # Verify mapping field input count.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM map.mapping_field mf
            JOIN map.mapping_field_input mfi
                ON mfi.mapping_field_id = mf.mapping_field_id
            WHERE mf.mapping_version_id = %s;
            """,
            (mapping_version_id,),
        )

        input_count = cursor.fetchone()[0]

        if input_count != 4:
            raise RuntimeError(
                f"Expected 4 mapping inputs, found {input_count}."
            )

        print("Mapping field input count: 4")

        # Verify all mapping fields are DIRECT.
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM map.mapping_field
            WHERE mapping_version_id = %s
              AND mapping_type_code <> 'DIRECT';
            """,
            (mapping_version_id,),
        )

        non_direct_count = cursor.fetchone()[0]

        if non_direct_count != 0:
            raise RuntimeError(
                "One or more customer fields are not DIRECT mappings."
            )

        print("Mapping type validation: all fields are DIRECT")


def main() -> None:
    """
    Main transaction coordinator.

    The complete mapping creation process runs inside one transaction.

    If any operation raises an exception:
        rollback occurs.

    If every operation succeeds:
        commit occurs.
    """

    print_section("CUSTOMER FULL-LOAD MAPPING CREATION")

    connection = None

    try:
        # Open the metadata-store connection.
        with get_metastore_connection() as connection:

            # Explicitly disable autocommit so all metadata changes
            # participate in one atomic transaction.
            connection.autocommit = False

            try:
                # Validate all prerequisite metadata.
                validate_prerequisites(connection)

                # Prevent duplicate mapping creation.
                check_existing_mapping(connection)

                # Create parent mapping and version.
                mapping_id, mapping_version_id = create_mapping(
                    connection
                )

                # Create the source definition.
                create_mapping_source(
                    connection,
                    mapping_version_id,
                )

                # Create four target mapping fields and four source inputs.
                create_mapping_fields(
                    connection,
                    mapping_version_id,
                )

                # Verify everything before committing.
                verify_mapping(
                    connection,
                    mapping_id,
                    mapping_version_id,
                )

                # Commit only after every validation succeeds.
                connection.commit()

                print_section("CUSTOMER MAPPING CREATION COMPLETED")
                print("Transaction status : COMMITTED")
                print(f"Mapping ID         : {mapping_id}")
                print(f"Mapping Version ID : {mapping_version_id}")
                print("Metadata creation  : PASSED")

            except Exception:
                # Roll back every metadata change made during this
                # transaction if any step fails.
                connection.rollback()

                print_section("CUSTOMER MAPPING CREATION FAILED")
                print("Transaction status : ROLLED BACK")

                raise

    except Exception as exc:
        # The exception is re-raised after rollback so the command exits
        # with a failure status and the actual error is visible.
        print(f"Error: {exc}")
        raise


# Execute the workflow when this module is run directly.
if __name__ == "__main__":
    main()