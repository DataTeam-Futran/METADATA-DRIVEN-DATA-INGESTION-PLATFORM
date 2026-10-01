"""
Create Customer Full Load Orchestration Metadata
=================================================

Purpose
-------
Creates the orchestration metadata required to execute the Customer
full-load ingestion.

Objects created
---------------
1. orch.pipeline
2. orch.pipeline_version
3. orch.pipeline_task

The task references:
    map.mapping_version.mapping_version_id = 2

Important
---------
This script creates the pipeline version in DRAFT status.

We intentionally do NOT publish the pipeline yet because validation
and execution checks should happen before publishing.
"""

# hashlib is used to generate a deterministic SHA-256 configuration hash.
# The hash provides an identifiable fingerprint for the pipeline version.
import hashlib

# json is used to build a deterministic representation of the pipeline
# configuration before calculating its SHA-256 hash.
import json

# PostgreSQL driver used to execute metadata SQL statements.
import psycopg

# Reuse the application's central metadata-store connection manager.
# This keeps database connection configuration in one place.
from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Pipeline constants
# ---------------------------------------------------------------------------
# These values define the business identity of the Customer ingestion
# pipeline. They are intentionally explicit because they are metadata,
# not runtime-generated values.
PIPELINE_CODE = "CUSTOMER_FULL_LOAD_PIPELINE"
PIPELINE_NAME = "Customer Full Load Pipeline"
PIPELINE_TYPE = "BATCH_MIGRATION"

# The pipeline itself can be ACTIVE while its first version remains DRAFT.
# This allows the pipeline identity to exist before a version is published.
PIPELINE_STATUS = "ACTIVE"

# ---------------------------------------------------------------------------
# Pipeline version configuration
# ---------------------------------------------------------------------------
# Pipeline versions are immutable once published, so version 1 is created
# separately from the stable pipeline identity.
VERSION_NUMBER = 1
VERSION_STATUS = "DRAFT"

# ---------------------------------------------------------------------------
# Customer mapping configuration
# ---------------------------------------------------------------------------
# This is the mapping version that was already validated during the
# previous development step.
MAPPING_VERSION_ID = 2

# ---------------------------------------------------------------------------
# Task configuration
# ---------------------------------------------------------------------------
# The task represents the actual full-load ingestion operation.
TASK_CODE = "CUSTOMER_FULL_LOAD"
TASK_NAME = "Customer Full Load"
TASK_TYPE = "FULL_LOAD"

# The first task in a pipeline uses sequence number 1.
TASK_SEQUENCE = 1

# If this task fails, the pipeline should stop.
TASK_ON_FAILURE = "STOP"

# The timeout matches the current execution configuration and the existing
# Employee full-load orchestration pattern inspected earlier.
TASK_TIMEOUT_SECONDS = 600


def calculate_pipeline_config_hash() -> str:
    """
    Generate a deterministic SHA-256 hash for the pipeline configuration.

    Why
    ---
    The pipeline_version table requires config_hash.

    We should not use a random value because the hash should represent
    the actual configuration of this pipeline version.

    sort_keys=True and separators=(",", ":") ensure that the same logical
    configuration produces the same hash.
    """

    # Build the exact configuration represented by pipeline version 1.
    configuration = {
        "pipeline_code": PIPELINE_CODE,
        "pipeline_type": PIPELINE_TYPE,
        "pipeline_status": PIPELINE_STATUS,
        "version_number": VERSION_NUMBER,
        "mapping_version_id": MAPPING_VERSION_ID,
        "task_code": TASK_CODE,
        "task_type": TASK_TYPE,
        "task_sequence": TASK_SEQUENCE,
        "task_on_failure": TASK_ON_FAILURE,
        "task_timeout_seconds": TASK_TIMEOUT_SECONDS,
    }

    # Convert the configuration to deterministic JSON.
    canonical_json = json.dumps(
        configuration,
        sort_keys=True,
        separators=(",", ":"),
    )

    # Generate a SHA-256 fingerprint of the canonical configuration.
    return hashlib.sha256(
        canonical_json.encode("utf-8")
    ).hexdigest()


def create_customer_orchestration() -> None:
    """
    Create the Customer pipeline, version, and full-load task.

    All three inserts are executed in one transaction.

    Why one transaction
    -------------------
    The pipeline, version, and task form one logical metadata unit.

    If any insert fails, the transaction is rolled back so we do not end
    up with a partially-created orchestration configuration.
    """

    # Calculate the pipeline version configuration hash before opening
    # the transaction.
    config_hash = calculate_pipeline_config_hash()

    print("=" * 100)
    print("CREATE CUSTOMER ORCHESTRATION")
    print("=" * 100)

    # Open the metadata-store connection using the application's
    # centralized connection manager.
    with get_metastore_connection() as connection:

        try:
            # Open a cursor for metadata operations.
            with connection.cursor() as cursor:

                # ------------------------------------------------------------------
                # Step 1: Insert the stable pipeline identity.
                # ------------------------------------------------------------------
                # pipeline_id is an identity column, so PostgreSQL generates it.
                cursor.execute(
                    """
                    INSERT INTO orch.pipeline (
                        tenant_id,
                        project_id,
                        pipeline_code,
                        pipeline_name,
                        status_code,
                        pipeline_type_code
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING pipeline_id;
                    """,
                    (
                        1,                  # tenant_id
                        1,                  # project_id
                        PIPELINE_CODE,
                        PIPELINE_NAME,
                        PIPELINE_STATUS,
                        PIPELINE_TYPE,
                    ),
                )

                # Capture the generated pipeline ID.
                pipeline_id = cursor.fetchone()[0]

                print(f"Pipeline created: pipeline_id={pipeline_id}")

                # ------------------------------------------------------------------
                # Step 2: Insert pipeline version.
                # ------------------------------------------------------------------
                # pipeline_version_id is also generated by PostgreSQL.
                cursor.execute(
                    """
                    INSERT INTO orch.pipeline_version (
                        tenant_id,
                        pipeline_id,
                        version_no,
                        status_code,
                        config_hash
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING pipeline_version_id;
                    """,
                    (
                        1,                  # tenant_id
                        pipeline_id,
                        VERSION_NUMBER,
                        VERSION_STATUS,
                        config_hash,
                    ),
                )

                # Capture the generated pipeline version ID.
                pipeline_version_id = cursor.fetchone()[0]

                print(
                    "Pipeline version created: "
                    f"pipeline_version_id={pipeline_version_id}"
                )

                # ------------------------------------------------------------------
                # Step 3: Insert the full-load task.
                # ------------------------------------------------------------------
                # The task references:
                #     pipeline_version_id
                #
                # and also:
                #     mapping_version_id = 2
                #
                # This connects orchestration to the already-created Customer
                # mapping configuration.
                cursor.execute(
                    """
                    INSERT INTO orch.pipeline_task (
                        tenant_id,
                        pipeline_version_id,
                        task_code,
                        task_name,
                        task_type_code,
                        mapping_version_id,
                        sequence_no,
                        on_failure_code,
                        retry_policy_id,
                        timeout_seconds,
                        task_config
                    )
                    VALUES (
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
                    RETURNING task_id;
                    """,
                    (
                        1,                      # tenant_id
                        pipeline_version_id,
                        TASK_CODE,
                        TASK_NAME,
                        TASK_TYPE,
                        MAPPING_VERSION_ID,
                        TASK_SEQUENCE,
                        TASK_ON_FAILURE,
                        None,                  # retry_policy_id
                        TASK_TIMEOUT_SECONDS,
                        None,                  # task_config
                    ),
                )

                # Capture the generated task ID.
                task_id = cursor.fetchone()[0]

                print(f"Pipeline task created: task_id={task_id}")

            # ------------------------------------------------------------------
            # Step 4: Commit the complete metadata transaction.
            # ------------------------------------------------------------------
            # Our metastore connection manager intentionally does not auto-commit.
            # Therefore the application explicitly commits the metadata changes.
            connection.commit()

            print()
            print("Transaction commit: PASSED")

        except Exception:
            # If anything fails, rollback prevents partial metadata creation.
            connection.rollback()

            print()
            print("Transaction rollback: EXECUTED")

            # Re-raise the original exception so the command fails visibly.
            raise

    # ----------------------------------------------------------------------
    # Final summary
    # ----------------------------------------------------------------------
    print()
    print("=" * 100)
    print("CUSTOMER ORCHESTRATION CREATED")
    print("=" * 100)
    print(f"Pipeline ID         : {pipeline_id}")
    print(f"Pipeline Code       : {PIPELINE_CODE}")
    print(f"Pipeline Version ID : {pipeline_version_id}")
    print(f"Version Number      : {VERSION_NUMBER}")
    print(f"Version Status      : {VERSION_STATUS}")
    print(f"Task ID             : {task_id}")
    print(f"Task Code           : {TASK_CODE}")
    print(f"Mapping Version ID  : {MAPPING_VERSION_ID}")
    print(f"Config Hash         : {config_hash}")
    print("=" * 100)


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------
# This allows the file to be executed with:
#
#     python -m scripts.metadata.create_customer_orchestration
#
# without executing the creation logic when the module is imported elsewhere.
if __name__ == "__main__":
    create_customer_orchestration()