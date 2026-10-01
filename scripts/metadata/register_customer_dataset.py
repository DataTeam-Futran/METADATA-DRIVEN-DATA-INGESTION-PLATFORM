"""
Customer Dataset Registration
==============================

Purpose:
    Register the Customer source dataset in the production-style
    catalog.dataset metadata table.

Confirmed POC context:
    Tenant      : 1
    Project     : 1
    Environment : 1 (DEV)
    System      : 1
    Source      : Connection 1
    Target      : Connection 11

Dataset being registered:
    Code        : CUSTOMER_DATASET
    Name        : Customer Dataset
    Type        : TABLE
    Role        : SOURCE
    Layer       : SOURCE

Important design points:
    1. dataset_id is NOT supplied because PostgreSQL generates it using
       GENERATED ALWAYS AS IDENTITY.
    2. dataset_uid is NOT supplied because PostgreSQL generates it using
       gen_random_uuid().
    3. created_at and updated_at use their database defaults.
    4. status_code uses the database default ACTIVE.
    5. The unique constraint on tenant_id + project_id + dataset_code
       prevents duplicate registration.
    6. The operation is transactional.
    7. The script is idempotent: running it again returns the existing
       dataset instead of creating a duplicate.

This script modifies only catalog.dataset.
It does NOT create the physical binding yet.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Confirmed metadata context
# ---------------------------------------------------------------------------
# These values were obtained from the previous read-only context inspection.
# They are explicitly defined here because this script is registering metadata
# for this specific POC context.
TENANT_ID = 1
PROJECT_ID = 1

# Stable metadata code for the Customer source dataset.
DATASET_CODE = "CUSTOMER_DATASET"


def main() -> None:
    """
    Register CUSTOMER_DATASET if it does not already exist.

    If the dataset already exists for the same tenant/project/code, the
    existing record is returned and no duplicate is created.
    """

    print("=" * 110)
    print("CUSTOMER DATASET REGISTRATION")
    print("=" * 110)

    # Open a metadata-store database connection.
    #
    # The connection manager intentionally does not auto-commit. This allows
    # this operation to control its own transaction boundary explicitly.
    with get_metastore_connection() as connection:

        try:
            # ----------------------------------------------------------------
            # 1. Check whether the dataset already exists
            # ----------------------------------------------------------------
            # This makes the operation idempotent. Running the script multiple
            # times will not create duplicate metadata.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        dataset_id,
                        dataset_uid,
                        tenant_id,
                        project_id,
                        dataset_code,
                        dataset_name,
                        object_type_code,
                        dataset_role_code,
                        layer_code,
                        status_code
                    FROM catalog.dataset
                    WHERE tenant_id = %s
                      AND project_id = %s
                      AND dataset_code = %s
                    FOR UPDATE;
                    """,
                    (
                        TENANT_ID,
                        PROJECT_ID,
                        DATASET_CODE,
                    ),
                )

                existing_row = cursor.fetchone()

            # ----------------------------------------------------------------
            # 2. Return existing dataset if already registered
            # ----------------------------------------------------------------
            if existing_row is not None:
                print("\nCustomer dataset already exists.")
                print("-" * 110)

                print(
                    f"Dataset ID      : {existing_row[0]}\n"
                    f"Dataset UID     : {existing_row[1]}\n"
                    f"Tenant ID       : {existing_row[2]}\n"
                    f"Project ID      : {existing_row[3]}\n"
                    f"Dataset Code    : {existing_row[4]}\n"
                    f"Dataset Name    : {existing_row[5]}\n"
                    f"Object Type     : {existing_row[6]}\n"
                    f"Dataset Role    : {existing_row[7]}\n"
                    f"Layer           : {existing_row[8]}\n"
                    f"Status          : {existing_row[9]}"
                )

                # Nothing new was created, but the transaction is still
                # committed cleanly before leaving the connection context.
                connection.commit()

                print("\nNo duplicate metadata was created.")
                return

            # ----------------------------------------------------------------
            # 3. Insert Customer dataset
            # ----------------------------------------------------------------
            # Notice that dataset_id and dataset_uid are intentionally omitted.
            #
            # PostgreSQL generates:
            #   dataset_id  -> identity sequence
            #   dataset_uid -> gen_random_uuid()
            #
            # status_code, timestamps, and row_version also use database
            # defaults.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO catalog.dataset
                    (
                        tenant_id,
                        project_id,
                        dataset_code,
                        dataset_name,
                        object_type_code,
                        dataset_role_code,
                        layer_code
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
                    RETURNING
                        dataset_id,
                        dataset_uid,
                        tenant_id,
                        project_id,
                        dataset_code,
                        dataset_name,
                        object_type_code,
                        dataset_role_code,
                        layer_code,
                        status_code;
                    """,
                    (
                        TENANT_ID,
                        PROJECT_ID,
                        DATASET_CODE,
                        "Customer Dataset",
                        "TABLE",
                        "SOURCE",
                        "SOURCE",
                    ),
                )

                inserted_row = cursor.fetchone()

            # ----------------------------------------------------------------
            # 4. Validate INSERT result
            # ----------------------------------------------------------------
            # RETURNING gives us the exact database-generated identifier and
            # values. We validate that PostgreSQL created the expected record
            # before committing the transaction.
            if inserted_row is None:
                raise RuntimeError(
                    "Customer dataset INSERT did not return a record."
                )

            print("\nCustomer dataset created successfully.")
            print("-" * 110)

            print(
                f"Dataset ID      : {inserted_row[0]}\n"
                f"Dataset UID     : {inserted_row[1]}\n"
                f"Tenant ID       : {inserted_row[2]}\n"
                f"Project ID      : {inserted_row[3]}\n"
                f"Dataset Code    : {inserted_row[4]}\n"
                f"Dataset Name    : {inserted_row[5]}\n"
                f"Object Type     : {inserted_row[6]}\n"
                f"Dataset Role    : {inserted_row[7]}\n"
                f"Layer           : {inserted_row[8]}\n"
                f"Status          : {inserted_row[9]}"
            )

            # ----------------------------------------------------------------
            # 5. Commit transaction
            # ----------------------------------------------------------------
            # The metadata write becomes permanent only after this commit.
            connection.commit()

            print("\nTransaction committed successfully.")

        except Exception:
            # ---------------------------------------------------------------
            # Roll back the entire transaction if anything fails.
            # ---------------------------------------------------------------
            #
            # This protects the metadata store from a partially completed
            # operation.
            connection.rollback()

            print("\nCustomer dataset registration failed.")
            print("Transaction rolled back.")

            # Re-raise the original exception so the command exits with a
            # failure status and the actual problem remains visible.
            raise

    print("\n" + "=" * 110)
    print("REGISTRATION COMPLETE")
    print("=" * 110)


if __name__ == "__main__":
    # Execute the registration operation when this module is run directly.
    main()

    