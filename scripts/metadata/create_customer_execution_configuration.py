"""
Customer Execution Configuration
================================

Purpose:
    Create the ingestion and target-load configuration for Customer
    mapping version 2.

Architecture:
    map.mapping_version
            |
            +--> ingest.load_config
            |
            +--> ingest.target_load_config

Why:
    The mapping defines WHAT fields move from source to target.
    These ingest tables define HOW the mapping should be executed.

Important:
    This script intentionally does not create pipeline/orchestration
    metadata. That will be handled in the next phase.

The operation is transactional:
    - Either both configuration records are created.
    - Or neither record is created.

The script is also idempotent:
    - If the configuration already exists, it validates the existing
      configuration instead of creating a duplicate.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Customer execution metadata identifiers.
#
# These values come from the already validated Customer mapping.
# ---------------------------------------------------------------------------
TENANT_ID = 1
MAPPING_VERSION_ID = 2


# ---------------------------------------------------------------------------
# Expected ingestion configuration.
#
# FULL_LOAD tells the runtime that the source should be completely read.
# truncate_before_load=True implements the truncate-insert strategy.
# ---------------------------------------------------------------------------
EXPECTED_LOAD_TYPE = "FULL_LOAD"
EXPECTED_BATCH_SIZE = 5000
EXPECTED_TRUNCATE = True
EXPECTED_ACTIVE = True


# ---------------------------------------------------------------------------
# Expected target-write configuration.
#
# TRUNCATE is explicitly supported by the database constraint and matches
# the mapping version's TRUNCATE_INSERT strategy.
# ---------------------------------------------------------------------------
EXPECTED_TARGET_CONFIG = {
    "tenant_id": TENANT_ID,
    "load_method_code": "AUTO",
    "commit_size": None,
    "auto_create_target": False,
    "alter_target_policy_code": "BLOCK",
    "transaction_mode_code": "AUTO",
    "write_timeout_seconds": 600,
    "target_prepare_action_code": "TRUNCATE",
    "target_schema_policy_code": "CREATE_IF_MISSING",
    "constraint_apply_policy_code": "APPLY_AFTER_LOAD",
    "index_apply_policy_code": "APPLY_AFTER_LOAD",
}


def validate_mapping_version(connection) -> None:
    """
    Verify that mapping version 2 exists and is the expected Customer
    mapping before writing any execution configuration.

    Why:
        Execution configuration must never be created against an unknown
        or invalid mapping version.
    """

    query = """
        SELECT
            mapping_id,
            tenant_id,
            version_no,
            primary_source_dataset_id,
            primary_source_schema_version_id,
            target_dataset_id,
            target_schema_version_id,
            datatype_mapping_set_id,
            load_type_code,
            load_strategy_code,
            status_code
        FROM map.mapping_version
        WHERE mapping_version_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (MAPPING_VERSION_ID,))
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Mapping version {MAPPING_VERSION_ID} does not exist."
        )

    (
        mapping_id,
        tenant_id,
        version_no,
        source_dataset_id,
        source_schema_version_id,
        target_dataset_id,
        target_schema_version_id,
        datatype_mapping_set_id,
        load_type_code,
        load_strategy_code,
        status_code,
    ) = row

    print()
    print("Mapping version validation:")
    print(f"  Mapping ID             : {mapping_id}")
    print(f"  Mapping Version ID     : {MAPPING_VERSION_ID}")
    print(f"  Tenant ID              : {tenant_id}")
    print(f"  Source Dataset ID      : {source_dataset_id}")
    print(f"  Target Dataset ID      : {target_dataset_id}")
    print(f"  Source Schema Version  : {source_schema_version_id}")
    print(f"  Target Schema Version  : {target_schema_version_id}")
    print(f"  Datatype Mapping Set   : {datatype_mapping_set_id}")
    print(f"  Load Type              : {load_type_code}")
    print(f"  Load Strategy          : {load_strategy_code}")
    print(f"  Status                 : {status_code}")

    # Make sure this is the Customer tenant/mapping we intend to configure.
    if tenant_id != TENANT_ID:
        raise RuntimeError(
            f"Mapping version {MAPPING_VERSION_ID} belongs to tenant "
            f"{tenant_id}, expected tenant {TENANT_ID}."
        )

    # The execution configuration is specifically for FULL_LOAD.
    if load_type_code != "FULL":
        raise RuntimeError(
            f"Unexpected mapping load type: {load_type_code}"
        )

    # The validated Customer mapping uses TRUNCATE_INSERT.
    if load_strategy_code != "TRUNCATE_INSERT":
        raise RuntimeError(
            f"Unexpected mapping load strategy: {load_strategy_code}"
        )


def create_or_validate_load_config(connection) -> None:
    """
    Create ingest.load_config for mapping version 2.

    If the record already exists, validate it instead of inserting another
    configuration record.

    Why:
        load_config does not have a unique constraint on mapping_version_id,
        so the application must prevent accidental duplicate configuration.
    """

    select_query = """
        SELECT
            load_config_id,
            mapping_version_id,
            load_type_code,
            batch_size,
            truncate_before_load,
            is_active
        FROM ingest.load_config
        WHERE mapping_version_id = %s
        ORDER BY load_config_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(select_query, (MAPPING_VERSION_ID,))
        rows = cursor.fetchall()

    if len(rows) > 1:
        raise RuntimeError(
            f"Multiple load_config records already exist for mapping "
            f"version {MAPPING_VERSION_ID}. Manual cleanup is required."
        )

    # Existing configuration: validate it rather than creating a duplicate.
    if len(rows) == 1:
        row = rows[0]

        print()
        print("ingest.load_config already exists:")
        print(f"  Load Config ID         : {row[0]}")
        print(f"  Mapping Version ID     : {row[1]}")
        print(f"  Load Type              : {row[2]}")
        print(f"  Batch Size             : {row[3]}")
        print(f"  Truncate Before Load   : {row[4]}")
        print(f"  Active                 : {row[5]}")

        expected = (
            MAPPING_VERSION_ID,
            EXPECTED_LOAD_TYPE,
            EXPECTED_BATCH_SIZE,
            EXPECTED_TRUNCATE,
            EXPECTED_ACTIVE,
        )

        actual = row[1:]

        if actual != expected:
            raise RuntimeError(
                "Existing ingest.load_config does not match the expected "
                "Customer execution configuration."
            )

        print("  Validation             : PASSED")
        return

    # No configuration exists, so create the Customer record.
    insert_query = """
        INSERT INTO ingest.load_config (
            mapping_version_id,
            load_type_code,
            batch_size,
            truncate_before_load,
            is_active
        )
        VALUES (%s, %s, %s, %s, %s)
        RETURNING load_config_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            insert_query,
            (
                MAPPING_VERSION_ID,
                EXPECTED_LOAD_TYPE,
                EXPECTED_BATCH_SIZE,
                EXPECTED_TRUNCATE,
                EXPECTED_ACTIVE,
            ),
        )

        load_config_id = cursor.fetchone()[0]

    print()
    print("ingest.load_config created:")
    print(f"  Load Config ID         : {load_config_id}")
    print(f"  Mapping Version ID     : {MAPPING_VERSION_ID}")
    print(f"  Load Type              : {EXPECTED_LOAD_TYPE}")
    print(f"  Batch Size             : {EXPECTED_BATCH_SIZE}")
    print(f"  Truncate Before Load   : {EXPECTED_TRUNCATE}")
    print(f"  Active                 : {EXPECTED_ACTIVE}")


def create_or_validate_target_load_config(connection) -> None:
    """
    Create ingest.target_load_config for mapping version 2.

    Existing configuration is validated rather than duplicated.

    Why:
        target_load_config has mapping_version_id as its primary key,
        so only one target execution configuration is allowed per mapping
        version.
    """

    select_query = """
        SELECT
            mapping_version_id,
            tenant_id,
            load_method_code,
            commit_size,
            auto_create_target,
            alter_target_policy_code,
            transaction_mode_code,
            write_timeout_seconds,
            target_prepare_action_code,
            target_schema_policy_code,
            constraint_apply_policy_code,
            index_apply_policy_code
        FROM ingest.target_load_config
        WHERE mapping_version_id = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(select_query, (MAPPING_VERSION_ID,))
        row = cursor.fetchone()

    expected = (
        MAPPING_VERSION_ID,
        EXPECTED_TARGET_CONFIG["tenant_id"],
        EXPECTED_TARGET_CONFIG["load_method_code"],
        EXPECTED_TARGET_CONFIG["commit_size"],
        EXPECTED_TARGET_CONFIG["auto_create_target"],
        EXPECTED_TARGET_CONFIG["alter_target_policy_code"],
        EXPECTED_TARGET_CONFIG["transaction_mode_code"],
        EXPECTED_TARGET_CONFIG["write_timeout_seconds"],
        EXPECTED_TARGET_CONFIG["target_prepare_action_code"],
        EXPECTED_TARGET_CONFIG["target_schema_policy_code"],
        EXPECTED_TARGET_CONFIG["constraint_apply_policy_code"],
        EXPECTED_TARGET_CONFIG["index_apply_policy_code"],
    )

    # Existing target configuration: validate it.
    if row is not None:
        print()
        print("ingest.target_load_config already exists.")

        if row != expected:
            raise RuntimeError(
                "Existing ingest.target_load_config does not match the "
                "expected Customer target execution configuration."
            )

        print("  Mapping Version ID     :", row[0])
        print("  Tenant ID              :", row[1])
        print("  Load Method            :", row[2])
        print("  Commit Size            :", row[3])
        print("  Auto Create Target     :", row[4])
        print("  Alter Policy           :", row[5])
        print("  Transaction Mode       :", row[6])
        print("  Write Timeout          :", row[7])
        print("  Prepare Action         :", row[8])
        print("  Schema Policy          :", row[9])
        print("  Constraint Policy      :", row[10])
        print("  Index Policy           :", row[11])
        print("  Validation             : PASSED")
        return

    # Insert the target execution strategy.
    insert_query = """
        INSERT INTO ingest.target_load_config (
            mapping_version_id,
            tenant_id,
            load_method_code,
            commit_size,
            auto_create_target,
            alter_target_policy_code,
            transaction_mode_code,
            write_timeout_seconds,
            target_prepare_action_code,
            target_schema_policy_code,
            constraint_apply_policy_code,
            index_apply_policy_code
        )
        VALUES (
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s
        );
    """

    with connection.cursor() as cursor:
        cursor.execute(
            insert_query,
            (
                MAPPING_VERSION_ID,
                EXPECTED_TARGET_CONFIG["tenant_id"],
                EXPECTED_TARGET_CONFIG["load_method_code"],
                EXPECTED_TARGET_CONFIG["commit_size"],
                EXPECTED_TARGET_CONFIG["auto_create_target"],
                EXPECTED_TARGET_CONFIG["alter_target_policy_code"],
                EXPECTED_TARGET_CONFIG["transaction_mode_code"],
                EXPECTED_TARGET_CONFIG["write_timeout_seconds"],
                EXPECTED_TARGET_CONFIG["target_prepare_action_code"],
                EXPECTED_TARGET_CONFIG["target_schema_policy_code"],
                EXPECTED_TARGET_CONFIG["constraint_apply_policy_code"],
                EXPECTED_TARGET_CONFIG["index_apply_policy_code"],
            ),
        )

    print()
    print("ingest.target_load_config created:")
    print(f"  Mapping Version ID     : {MAPPING_VERSION_ID}")
    print(f"  Tenant ID              : {TENANT_ID}")
    print(
        "  Load Method            : "
        f"{EXPECTED_TARGET_CONFIG['load_method_code']}"
    )
    print(
        "  Commit Size            : "
        f"{EXPECTED_TARGET_CONFIG['commit_size']}"
    )
    print(
        "  Auto Create Target     : "
        f"{EXPECTED_TARGET_CONFIG['auto_create_target']}"
    )
    print(
        "  Alter Policy           : "
        f"{EXPECTED_TARGET_CONFIG['alter_target_policy_code']}"
    )
    print(
        "  Transaction Mode       : "
        f"{EXPECTED_TARGET_CONFIG['transaction_mode_code']}"
    )
    print(
        "  Write Timeout          : "
        f"{EXPECTED_TARGET_CONFIG['write_timeout_seconds']}"
    )
    print(
        "  Prepare Action         : "
        f"{EXPECTED_TARGET_CONFIG['target_prepare_action_code']}"
    )
    print(
        "  Schema Policy          : "
        f"{EXPECTED_TARGET_CONFIG['target_schema_policy_code']}"
    )
    print(
        "  Constraint Policy      : "
        f"{EXPECTED_TARGET_CONFIG['constraint_apply_policy_code']}"
    )
    print(
        "  Index Policy           : "
        f"{EXPECTED_TARGET_CONFIG['index_apply_policy_code']}"
    )


def main() -> None:
    """
    Create both Customer execution configuration records in one transaction.

    If anything fails:
        rollback() ensures that we do not leave half-created configuration.
    """

    print("=" * 100)
    print("CUSTOMER EXECUTION CONFIGURATION")
    print("=" * 100)

    with get_metastore_connection() as connection:
        try:
            # Validate the mapping before changing execution metadata.
            validate_mapping_version(connection)

            # Create or validate source/load execution configuration.
            create_or_validate_load_config(connection)

            # Create or validate target write execution configuration.
            create_or_validate_target_load_config(connection)

            # Explicit commit is required because the generic metastore
            # connection manager intentionally does not auto-commit.
            connection.commit()

            print()
            print("=" * 100)
            print("CUSTOMER EXECUTION CONFIGURATION COMMITTED")
            print("Mapping Version       : 2")
            print("Load Type             : FULL_LOAD")
            print("Load Strategy         : TRUNCATE_INSERT")
            print("Target Prepare Action : TRUNCATE")
            print("=" * 100)

        except Exception:
            # Roll back BOTH configuration changes if any validation or
            # database operation fails.
            connection.rollback()

            print()
            print("Execution configuration failed.")
            print("Transaction rolled back.")
            raise


# ---------------------------------------------------------------------------
# Standard Python module entry point.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()