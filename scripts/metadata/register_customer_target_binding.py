"""
Customer Target Dataset Binding Registration

Purpose:
    Register the physical target location for CUSTOMER_TARGET_DATASET.

Logical flow:

    Target Dataset 8
        ↓
    Target Binding
        ↓
    Connection 11
        ↓
    ingestion_metastore
        ↓
    warehouse.customer_target

Why this is required:
    catalog.dataset identifies WHAT the dataset represents.
    catalog.dataset_binding identifies WHERE the dataset physically exists.

Important:
    - Connection 11 is the existing dynamic TARGET connection.
    - No credentials are handled directly by this script.
    - The physical target table does not need to exist yet.
    - PostgreSQL generates dataset_binding_id automatically.
    - The operation is transactional.
    - This script is idempotent for the same dataset/environment combination.
    - project_id belongs to catalog.dataset, not conn.connection_profile.
"""

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Existing target metadata identifiers
# ---------------------------------------------------------------------------

# Tenant used by the Customer POC.
TENANT_ID = 1

# Project used by the Customer POC.
PROJECT_ID = 1

# Target dataset created in the previous step.
TARGET_DATASET_ID = 8

# Existing dynamic target connection.
TARGET_CONNECTION_ID = 11

# Existing development environment.
ENVIRONMENT_ID = 1

# Physical target database.
TARGET_DATABASE = "ingestion_metastore"

# Physical target schema.
TARGET_SCHEMA = "warehouse"

# Physical target table.
#
# The table does not need to exist yet.
# The target-schema-generation step will handle the physical table later.
TARGET_OBJECT = "customer_target"

# Binding becomes active after successful registration.
STATUS_CODE = "ACTIVE"


def get_target_connection(
    connection: Any,
) -> dict[str, Any]:
    """
    Read and validate the target connection.

    Why:
        The binding must point to an existing active TARGET connection.

    Important:
        conn.connection_profile contains tenant, system, environment,
        connector and connection information, but it does NOT contain
        project_id.

        Project ownership is validated separately through catalog.dataset.
    """

    # -----------------------------------------------------------------------
    # Query the authoritative connection metadata.
    #
    # project_id is intentionally NOT selected because it does not exist
    # in conn.connection_profile.
    # -----------------------------------------------------------------------
    query = """
        SELECT
            connection_id,
            tenant_id,
            system_id,
            environment_id,
            connection_role_code,
            connection_name,
            database_name,
            status_code
        FROM conn.connection_profile
        WHERE connection_id = %s
        LIMIT 1;
    """

    # Execute the connection lookup.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (TARGET_CONNECTION_ID,),
        )

        # Fetch the target connection record.
        row = cursor.fetchone()

    # Stop if the target connection does not exist.
    if row is None:
        raise LookupError(
            f"Target Connection {TARGET_CONNECTION_ID} was not found."
        )

    # -----------------------------------------------------------------------
    # Build a readable connection metadata dictionary.
    #
    # project_id is intentionally absent because the connection profile
    # does not own project information.
    # -----------------------------------------------------------------------
    target_connection = {
        "connection_id": row[0],
        "tenant_id": row[1],
        "system_id": row[2],
        "environment_id": row[3],
        "connection_role_code": row[4],
        "connection_name": row[5],
        "database_name": row[6],
        "status_code": row[7],
    }

    # -----------------------------------------------------------------------
    # Validate tenant ownership.
    #
    # The target connection and target dataset must belong to the same
    # tenant for this POC.
    # -----------------------------------------------------------------------
    if target_connection["tenant_id"] != TENANT_ID:
        raise ValueError(
            "Target connection tenant does not match the target dataset tenant."
        )

    # -----------------------------------------------------------------------
    # Validate connection role.
    #
    # TARGET is required. BOTH is also valid because such a connection can
    # participate in both source and target operations.
    # -----------------------------------------------------------------------
    if target_connection["connection_role_code"] not in (
        "TARGET",
        "BOTH",
    ):
        raise ValueError(
            "Connection 11 is not configured as TARGET or BOTH."
        )

    # -----------------------------------------------------------------------
    # Only active connections can be used for a new binding.
    # -----------------------------------------------------------------------
    if target_connection["status_code"] != "ACTIVE":
        raise ValueError(
            "Target connection is not ACTIVE."
        )

    # -----------------------------------------------------------------------
    # Validate that the target connection points to the expected database.
    # -----------------------------------------------------------------------
    if target_connection["database_name"] != TARGET_DATABASE:
        raise ValueError(
            "Target connection database does not match "
            f"'{TARGET_DATABASE}'."
        )

    return target_connection


def validate_target_dataset(
    connection: Any,
) -> None:
    """
    Validate that Dataset 8 exists and is an active TARGET dataset.

    Why:
        A physical binding should never be created for an invalid logical
        dataset.

        This is also where project ownership is validated because project_id
        belongs to catalog.dataset.
    """

    # -----------------------------------------------------------------------
    # Query the authoritative target dataset metadata.
    # -----------------------------------------------------------------------
    query = """
        SELECT
            dataset_id,
            tenant_id,
            project_id,
            dataset_code,
            dataset_role_code,
            object_type_code,
            layer_code,
            status_code
        FROM catalog.dataset
        WHERE dataset_id = %s
        LIMIT 1;
    """

    # Execute the dataset lookup.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (TARGET_DATASET_ID,),
        )

        # Fetch the dataset metadata.
        row = cursor.fetchone()

    # Stop if Dataset 8 does not exist.
    if row is None:
        raise LookupError(
            f"Target Dataset {TARGET_DATASET_ID} was not found."
        )

    # -----------------------------------------------------------------------
    # Validate tenant ownership.
    # -----------------------------------------------------------------------
    if row[1] != TENANT_ID:
        raise ValueError(
            "Target dataset does not belong to Tenant 1."
        )

    # -----------------------------------------------------------------------
    # Validate project ownership.
    #
    # This is the correct location for project validation because
    # catalog.dataset contains project_id.
    # -----------------------------------------------------------------------
    if row[2] != PROJECT_ID:
        raise ValueError(
            "Target dataset does not belong to Project 1."
        )

    # -----------------------------------------------------------------------
    # Validate the dataset role.
    # -----------------------------------------------------------------------
    if row[4] != "TARGET":
        raise ValueError(
            "Dataset 8 is not configured as a TARGET dataset."
        )

    # -----------------------------------------------------------------------
    # Validate the physical object type.
    # -----------------------------------------------------------------------
    if row[5] != "TABLE":
        raise ValueError(
            "Customer target dataset must represent a TABLE."
        )

    # -----------------------------------------------------------------------
    # Validate active status.
    # -----------------------------------------------------------------------
    if row[7] != "ACTIVE":
        raise ValueError(
            "Target dataset is not ACTIVE."
        )

    # Display the validated target dataset.
    print(f"Target Dataset ID : {row[0]}")
    print(f"Dataset Code      : {row[3]}")
    print(f"Dataset Role      : {row[4]}")
    print(f"Object Type       : {row[5]}")
    print(f"Layer             : {row[6]}")
    print(f"Status            : {row[7]}")


def find_existing_binding(
    connection: Any,
) -> int | None:
    """
    Check whether the target dataset already has a binding in Environment 1.

    Why:
        catalog.dataset_binding has a uniqueness model around the
        dataset/environment combination.

        Checking first makes this operation safe to execute more than once.
    """

    # -----------------------------------------------------------------------
    # Search for an existing binding.
    # -----------------------------------------------------------------------
    query = """
        SELECT
            dataset_binding_id
        FROM catalog.dataset_binding
        WHERE dataset_id = %s
          AND environment_id = %s
        LIMIT 1;
    """

    # Execute the lookup.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TARGET_DATASET_ID,
                ENVIRONMENT_ID,
            ),
        )

        # Fetch the existing binding if one exists.
        row = cursor.fetchone()

    # Return the existing identity-generated binding ID.
    if row is not None:
        return int(row[0])

    # No binding currently exists.
    return None


def create_target_binding(
    connection: Any,
) -> int:
    """
    Create the target physical binding.

    Returns:
        The PostgreSQL-generated dataset_binding_id.
    """

    # -----------------------------------------------------------------------
    # Check whether the binding already exists.
    # -----------------------------------------------------------------------
    existing_binding_id = find_existing_binding(
        connection
    )

    # -----------------------------------------------------------------------
    # Do not create a duplicate binding.
    # -----------------------------------------------------------------------
    if existing_binding_id is not None:
        print(
            f"Target binding already exists. "
            f"Binding ID: {existing_binding_id}"
        )

        return existing_binding_id

    # -----------------------------------------------------------------------
    # Insert the target binding.
    #
    # dataset_binding_id is intentionally omitted because PostgreSQL
    # generates the identity value automatically.
    # -----------------------------------------------------------------------
    query = """
        INSERT INTO catalog.dataset_binding (
            tenant_id,
            dataset_id,
            environment_id,
            connection_id,
            catalog_name,
            schema_name,
            object_name,
            object_name_normalized,
            status_code
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
            %s
        )
        RETURNING dataset_binding_id;
    """

    # Execute the metadata insert.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TENANT_ID,
                TARGET_DATASET_ID,
                ENVIRONMENT_ID,
                TARGET_CONNECTION_ID,
                TARGET_DATABASE,
                TARGET_SCHEMA,
                TARGET_OBJECT,
                TARGET_OBJECT.lower(),
                STATUS_CODE,
            ),
        )

        # Read the identity-generated binding ID.
        binding_id = cursor.fetchone()[0]

    return int(binding_id)


def main() -> None:
    """
    Register the Customer target binding transactionally.
    """

    # -----------------------------------------------------------------------
    # Display the operation heading.
    # -----------------------------------------------------------------------
    print("=" * 90)
    print("CUSTOMER TARGET DATASET BINDING REGISTRATION")
    print("=" * 90)

    # -----------------------------------------------------------------------
    # Open the metadata-store connection.
    #
    # The connection manager does not auto-commit, so this function
    # explicitly commits on success and rolls back on failure.
    # -----------------------------------------------------------------------
    with get_metastore_connection() as connection:

        try:
            # ===============================================================
            # 1. Validate the target connection.
            # ===============================================================
            print()
            print("TARGET CONNECTION VALIDATION")
            print("-" * 90)

            target_connection = get_target_connection(
                connection
            )

            # Display safe target connection metadata.
            print(
                f"Connection ID      : "
                f"{target_connection['connection_id']}"
            )

            print(
                f"Connection Name    : "
                f"{target_connection['connection_name']}"
            )

            print(
                f"System ID          : "
                f"{target_connection['system_id']}"
            )

            print(
                f"Environment ID     : "
                f"{target_connection['environment_id']}"
            )

            print(
                f"Role               : "
                f"{target_connection['connection_role_code']}"
            )

            print(
                f"Database           : "
                f"{target_connection['database_name']}"
            )

            print(
                f"Status             : "
                f"{target_connection['status_code']}"
            )

            # ===============================================================
            # 2. Validate the target dataset.
            # ===============================================================
            print()
            print("TARGET DATASET VALIDATION")
            print("-" * 90)

            validate_target_dataset(
                connection
            )

            # ===============================================================
            # 3. Register the physical target binding.
            # ===============================================================
            print()
            print("TARGET BINDING")
            print("-" * 90)

            binding_id = create_target_binding(
                connection
            )

            # Display the binding metadata.
            print(f"Binding ID         : {binding_id}")
            print(f"Dataset ID         : {TARGET_DATASET_ID}")
            print(f"Environment ID     : {ENVIRONMENT_ID}")
            print(f"Connection ID      : {TARGET_CONNECTION_ID}")
            print(f"Database           : {TARGET_DATABASE}")
            print(f"Schema             : {TARGET_SCHEMA}")
            print(f"Object             : {TARGET_OBJECT}")
            print(f"Status             : {STATUS_CODE}")

            # ===============================================================
            # 4. Commit the complete metadata transaction.
            # ===============================================================
            connection.commit()

            print()
            print("=" * 90)
            print("TRANSACTION COMMITTED SUCCESSFULLY")
            print("TARGET BINDING REGISTRATION COMPLETE")
            print("=" * 90)

        except Exception:
            # ----------------------------------------------------------------
            # Roll back all metadata changes when anything fails.
            # ----------------------------------------------------------------
            connection.rollback()

            # Re-raise the original exception for troubleshooting.
            raise


# ---------------------------------------------------------------------------
# Execute the registration when this module is run directly.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()