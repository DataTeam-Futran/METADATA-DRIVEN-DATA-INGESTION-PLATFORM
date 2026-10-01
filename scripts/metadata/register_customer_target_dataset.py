"""
Customer Target Dataset Registration

Purpose:
    Register the logical Customer target dataset in the production-style
    catalog metadata.

Why this is required:
    The ingestion runtime should resolve the target through metadata instead
    of hardcoding a physical target table.

Target metadata created by this script:
    Tenant 1
        ↓
    Project 1
        ↓
    CUSTOMER_TARGET_DATASET

Important:
    - Uses the existing Tenant 1 / Project 1 context.
    - Does not create a database connection.
    - Does not create a physical PostgreSQL table.
    - PostgreSQL generates dataset_id automatically.
    - The operation is transactional.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Target dataset metadata
# ---------------------------------------------------------------------------

# Existing tenant used by the Customer POC.
TENANT_ID = 1

# Existing project used by the Customer POC.
PROJECT_ID = 1

# Logical code used to identify the target dataset.
DATASET_CODE = "CUSTOMER_TARGET_DATASET"

# Human-readable target dataset name.
DATASET_NAME = "Customer Target Dataset"

# The target represents a physical relational table.
OBJECT_TYPE_CODE = "TABLE"

# This dataset is a target dataset.
DATASET_ROLE_CODE = "TARGET"

# The POC target is intended for the curated layer.
LAYER_CODE = "CURATED"

# The dataset is immediately active after registration.
STATUS_CODE = "ACTIVE"


def find_existing_dataset(connection) -> int | None:
    """
    Check whether the target dataset is already registered.

    Why:
        This makes the registration operation idempotent and prevents
        duplicate logical target datasets.
    """

    # Query the authoritative catalog dataset table.
    query = """
        SELECT
            dataset_id
        FROM catalog.dataset
        WHERE tenant_id = %s
          AND project_id = %s
          AND dataset_code = %s
        LIMIT 1;
    """

    # Execute the read-only lookup.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TENANT_ID,
                PROJECT_ID,
                DATASET_CODE,
            ),
        )

        # Read the existing dataset if one is present.
        row = cursor.fetchone()

    # Return the existing dataset ID.
    if row is not None:
        return int(row[0])

    # No existing dataset was found.
    return None


def create_target_dataset(connection) -> int:
    """
    Create the logical Customer target dataset.

    Returns:
        The PostgreSQL-generated dataset_id.
    """

    # First check for an existing dataset.
    existing_dataset_id = find_existing_dataset(connection)

    # Do not create a duplicate dataset.
    if existing_dataset_id is not None:
        print(
            f"Target dataset already exists. "
            f"Dataset ID: {existing_dataset_id}"
        )
        return existing_dataset_id

    # Insert the logical target dataset.
    #
    # dataset_id is intentionally omitted because the catalog table uses
    # PostgreSQL identity generation.
    query = """
        INSERT INTO catalog.dataset (
            tenant_id,
            project_id,
            dataset_code,
            dataset_name,
            object_type_code,
            dataset_role_code,
            layer_code,
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
            %s
        )
        RETURNING dataset_id;
    """

    # Execute the metadata insert.
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TENANT_ID,
                PROJECT_ID,
                DATASET_CODE,
                DATASET_NAME,
                OBJECT_TYPE_CODE,
                DATASET_ROLE_CODE,
                LAYER_CODE,
                STATUS_CODE,
            ),
        )

        # Read the identity-generated dataset ID.
        dataset_id = cursor.fetchone()[0]

    # Return the generated dataset identifier.
    return int(dataset_id)


def main() -> None:
    """
    Register the Customer target dataset transactionally.
    """

    # Print the operation heading.
    print("=" * 90)
    print("CUSTOMER TARGET DATASET REGISTRATION")
    print("=" * 90)

    # Open the metadata-store transaction.
    with get_metastore_connection() as connection:

        try:
            # Create or resolve the target dataset.
            dataset_id = create_target_dataset(connection)

            # Commit the metadata change explicitly.
            connection.commit()

            # Display the resulting metadata.
            print()
            print("TARGET DATASET")
            print("-" * 90)
            print(f"Dataset ID       : {dataset_id}")
            print(f"Tenant ID        : {TENANT_ID}")
            print(f"Project ID       : {PROJECT_ID}")
            print(f"Dataset Code     : {DATASET_CODE}")
            print(f"Dataset Name     : {DATASET_NAME}")
            print(f"Object Type      : {OBJECT_TYPE_CODE}")
            print(f"Dataset Role     : {DATASET_ROLE_CODE}")
            print(f"Layer            : {LAYER_CODE}")
            print(f"Status           : {STATUS_CODE}")

            print()
            print("TRANSACTION COMMITTED SUCCESSFULLY")
            print("TARGET DATASET REGISTRATION COMPLETE")

        except Exception:
            # Roll back the entire transaction if registration fails.
            connection.rollback()

            # Re-raise the original exception for troubleshooting.
            raise


# Execute the registration when the module is run directly.
if __name__ == "__main__":
    main()