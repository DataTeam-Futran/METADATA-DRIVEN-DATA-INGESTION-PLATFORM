"""
Customer Dataset Binding Registration
======================================

Purpose:
    Register the physical source location of CUSTOMER_DATASET in
    catalog.dataset_binding.

Confirmed metadata context:
    Tenant ID        : 1
    Project ID       : 1
    Environment ID   : 1 (DEV)
    System ID        : 1
    Dataset ID       : 7
    Source Connection: 1

Physical source:
    Database         : demo_source_db
    Schema           : public
    Object           : customer

Architecture:
    catalog.dataset
        |
        +--> catalog.dataset_binding
                |
                +--> conn.connection_profile
                         |
                         +--> Connection 1

Important:
    dataset_binding_id is GENERATED ALWAYS AS IDENTITY, so this script
    intentionally does not supply that value.

    The operation is transactional and idempotent.
    Running the script again will return the existing binding instead of
    creating a duplicate.

This script modifies only catalog.dataset_binding.
It does not modify the source database.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Confirmed metadata context
# ---------------------------------------------------------------------------
# These values were established through the previous read-only inspection
# scripts and the successfully created catalog.dataset record.
TENANT_ID = 1
DATASET_ID = 7
ENVIRONMENT_ID = 1
CONNECTION_ID = 1

# ---------------------------------------------------------------------------
# Physical source location
# ---------------------------------------------------------------------------
# These values represent the actual Customer table discovered through the
# dynamic PostgreSQL source connection.
CATALOG_NAME = "demo_source_db"
SCHEMA_NAME = "public"
OBJECT_NAME = "customer"


def main() -> None:
    """
    Create the physical Customer dataset binding if it does not exist.

    The function performs:
        1. Existing binding check.
        2. Source connection validation.
        3. Binding insertion.
        4. Insert-result validation.
        5. Transaction commit.

    Any failure causes the transaction to roll back.
    """

    print("=" * 110)
    print("CUSTOMER DATASET BINDING REGISTRATION")
    print("=" * 110)

    # Open the metadata database connection.
    #
    # The metastore connection manager does not auto-commit. This allows
    # this operation to explicitly control its transaction boundary.
    with get_metastore_connection() as connection:

        try:
            # ----------------------------------------------------------------
            # 1. Validate the referenced source connection
            # ----------------------------------------------------------------
            # The binding has a foreign key to conn.connection_profile.
            #
            # We additionally validate the connection role here because this
            # binding represents a source dataset.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
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
                    FOR UPDATE;
                    """,
                    (CONNECTION_ID,),
                )

                connection_row = cursor.fetchone()

            if connection_row is None:
                raise LookupError(
                    f"Source connection {CONNECTION_ID} does not exist."
                )

            # Validate that the connection belongs to the same tenant and
            # environment as the dataset binding we are creating.
            if connection_row[1] != TENANT_ID:
                raise ValueError(
                    "Source connection tenant does not match dataset tenant."
                )

            if connection_row[3] != ENVIRONMENT_ID:
                raise ValueError(
                    "Source connection environment does not match binding "
                    "environment."
                )

            if connection_row[4] not in ("SOURCE", "BOTH"):
                raise ValueError(
                    f"Connection {CONNECTION_ID} is not configured as a "
                    f"source connection. Role: {connection_row[4]}"
                )

            if connection_row[7] != "ACTIVE":
                raise ValueError(
                    f"Source connection {CONNECTION_ID} is not ACTIVE. "
                    f"Status: {connection_row[7]}"
                )

            print("\nSource connection validation passed.")
            print("-" * 110)
            print(
                f"Connection ID   : {connection_row[0]}\n"
                f"Tenant ID       : {connection_row[1]}\n"
                f"System ID       : {connection_row[2]}\n"
                f"Environment ID  : {connection_row[3]}\n"
                f"Connection Role : {connection_row[4]}\n"
                f"Connection Name : {connection_row[5]}\n"
                f"Database        : {connection_row[6]}\n"
                f"Status          : {connection_row[7]}"
            )

            # ----------------------------------------------------------------
            # 2. Validate the Customer dataset
            # ----------------------------------------------------------------
            # The binding must point to an existing dataset.
            #
            # This explicit validation gives us a clearer application-level
            # error than relying only on the database foreign-key violation.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        dataset_id,
                        tenant_id,
                        project_id,
                        dataset_code,
                        dataset_name,
                        dataset_role_code,
                        status_code
                    FROM catalog.dataset
                    WHERE dataset_id = %s
                    FOR UPDATE;
                    """,
                    (DATASET_ID,),
                )

                dataset_row = cursor.fetchone()

            if dataset_row is None:
                raise LookupError(
                    f"Customer dataset {DATASET_ID} does not exist."
                )

            if dataset_row[1] != TENANT_ID:
                raise ValueError(
                    "Customer dataset tenant does not match binding tenant."
                )

            if dataset_row[3] != "CUSTOMER_DATASET":
                raise ValueError(
                    "Dataset ID does not reference CUSTOMER_DATASET."
                )

            if dataset_row[5] != "SOURCE":
                raise ValueError(
                    "Customer dataset is not configured as a SOURCE dataset."
                )

            if dataset_row[6] != "ACTIVE":
                raise ValueError(
                    f"Customer dataset is not ACTIVE. Status: {dataset_row[6]}"
                )

            print("\nCustomer dataset validation passed.")
            print("-" * 110)
            print(
                f"Dataset ID      : {dataset_row[0]}\n"
                f"Tenant ID       : {dataset_row[1]}\n"
                f"Project ID      : {dataset_row[2]}\n"
                f"Dataset Code    : {dataset_row[3]}\n"
                f"Dataset Name    : {dataset_row[4]}\n"
                f"Dataset Role    : {dataset_row[5]}\n"
                f"Status          : {dataset_row[6]}"
            )

            # ----------------------------------------------------------------
            # 3. Check whether the binding already exists
            # ----------------------------------------------------------------
            # The table has a unique constraint around dataset/environment,
            # so this check makes the application behavior explicitly
            # idempotent before attempting the INSERT.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
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
                    WHERE dataset_id = %s
                      AND environment_id = %s
                    FOR UPDATE;
                    """,
                    (
                        DATASET_ID,
                        ENVIRONMENT_ID,
                    ),
                )

                existing_binding = cursor.fetchone()

            # ----------------------------------------------------------------
            # 4. Return the existing binding if already registered
            # ----------------------------------------------------------------
            if existing_binding is not None:
                print("\nCustomer dataset binding already exists.")
                print("-" * 110)

                print(
                    f"Binding ID          : {existing_binding[0]}\n"
                    f"Tenant ID           : {existing_binding[1]}\n"
                    f"Dataset ID          : {existing_binding[2]}\n"
                    f"Environment ID      : {existing_binding[3]}\n"
                    f"Connection ID       : {existing_binding[4]}\n"
                    f"Catalog Name        : {existing_binding[5]}\n"
                    f"Schema Name         : {existing_binding[6]}\n"
                    f"Object Name         : {existing_binding[7]}\n"
                    f"Normalized Object   : {existing_binding[8]}\n"
                    f"Status              : {existing_binding[9]}"
                )

                # No new metadata was created.
                connection.commit()

                print("\nNo duplicate binding was created.")
                return

            # ----------------------------------------------------------------
            # 5. Insert the physical binding
            # ----------------------------------------------------------------
            # dataset_binding_id is generated by PostgreSQL because the
            # column is GENERATED ALWAYS AS IDENTITY.
            #
            # object_name_normalized is explicitly populated so the catalog
            # has a normalized lookup value for physical object matching.
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO catalog.dataset_binding
                    (
                        tenant_id,
                        dataset_id,
                        environment_id,
                        connection_id,
                        catalog_name,
                        schema_name,
                        object_name,
                        object_name_normalized
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
                        %s
                    )
                    RETURNING
                        dataset_binding_id,
                        tenant_id,
                        dataset_id,
                        environment_id,
                        connection_id,
                        catalog_name,
                        schema_name,
                        object_name,
                        object_name_normalized,
                        status_code;
                    """,
                    (
                        TENANT_ID,
                        DATASET_ID,
                        ENVIRONMENT_ID,
                        CONNECTION_ID,
                        CATALOG_NAME,
                        SCHEMA_NAME,
                        OBJECT_NAME,
                        OBJECT_NAME.lower(),
                    ),
                )

                inserted_binding = cursor.fetchone()

            # ----------------------------------------------------------------
            # 6. Validate INSERT result
            # ----------------------------------------------------------------
            # RETURNING gives us the exact generated binding ID and persisted
            # values before the transaction is committed.
            if inserted_binding is None:
                raise RuntimeError(
                    "Dataset binding INSERT did not return a record."
                )

            print("\nCustomer dataset binding created successfully.")
            print("-" * 110)

            print(
                f"Binding ID          : {inserted_binding[0]}\n"
                f"Tenant ID           : {inserted_binding[1]}\n"
                f"Dataset ID          : {inserted_binding[2]}\n"
                f"Environment ID      : {inserted_binding[3]}\n"
                f"Connection ID       : {inserted_binding[4]}\n"
                f"Catalog Name        : {inserted_binding[5]}\n"
                f"Schema Name         : {inserted_binding[6]}\n"
                f"Object Name         : {inserted_binding[7]}\n"
                f"Normalized Object   : {inserted_binding[8]}\n"
                f"Status              : {inserted_binding[9]}"
            )

            # ----------------------------------------------------------------
            # 7. Commit transaction
            # ----------------------------------------------------------------
            # The binding becomes permanent only after the explicit commit.
            connection.commit()

            print("\nTransaction committed successfully.")

        except Exception:
            # ---------------------------------------------------------------
            # Roll back any changes if validation or INSERT fails.
            # ---------------------------------------------------------------
            connection.rollback()

            print("\nCustomer dataset binding registration failed.")
            print("Transaction rolled back.")

            # Preserve the original exception and traceback for debugging.
            raise

    print("\n" + "=" * 110)
    print("BINDING REGISTRATION COMPLETE")
    print("=" * 110)


if __name__ == "__main__":
    # Run the registration operation when this module is executed directly.
    main()