"""
Customer Target Binding Verification

Purpose:
    Verify that the Customer target dataset is correctly connected to the
    existing dynamic target connection through catalog.dataset_binding.

What this verifies:
    1. Target dataset exists.
    2. Target binding exists.
    3. Binding points to Connection 11.
    4. Binding points to Environment 1.
    5. Physical target location is ingestion_metastore.warehouse.customer_target.

Important:
    This script is READ-ONLY.
    It does not create or modify metadata.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Expected target metadata
# ---------------------------------------------------------------------------

# Target dataset created earlier.
TARGET_DATASET_ID = 8

# Target binding created in the previous step.
TARGET_BINDING_ID = 8

# Existing dynamic target connection.
TARGET_CONNECTION_ID = 11

# Existing development environment.
ENVIRONMENT_ID = 1

# Expected target database.
TARGET_DATABASE = "ingestion_metastore"

# Expected target schema.
TARGET_SCHEMA = "warehouse"

# Expected target object.
TARGET_OBJECT = "customer_target"


def main() -> None:
    """
    Verify the Customer target dataset binding.
    """

    # Display the verification heading.
    print("=" * 90)
    print("CUSTOMER TARGET BINDING VERIFICATION")
    print("=" * 90)

    # Open a read-only metadata-store connection.
    with get_metastore_connection() as connection:

        # ================================================================
        # 1. Read target dataset and binding together.
        # ================================================================
        query = """
            SELECT
                d.dataset_id,
                d.tenant_id,
                d.project_id,
                d.dataset_code,
                d.dataset_name,
                d.dataset_role_code,
                d.object_type_code,
                d.layer_code,
                d.status_code,

                b.dataset_binding_id,
                b.environment_id,
                b.connection_id,
                b.catalog_name,
                b.schema_name,
                b.object_name,
                b.object_name_normalized,
                b.status_code

            FROM catalog.dataset AS d

            INNER JOIN catalog.dataset_binding AS b
                ON b.dataset_id = d.dataset_id

            WHERE d.dataset_id = %s
              AND b.dataset_binding_id = %s;
        """

        # Execute the verification query.
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    TARGET_DATASET_ID,
                    TARGET_BINDING_ID,
                ),
            )

            # Fetch the target dataset/binding record.
            row = cursor.fetchone()

        # Stop if the expected metadata does not exist.
        if row is None:
            raise LookupError(
                "Expected Customer target dataset/binding was not found."
            )

        # ================================================================
        # 2. Display dataset metadata.
        # ================================================================
        print()
        print("=" * 90)
        print("TARGET DATASET")
        print("=" * 90)

        print(f"Dataset ID        : {row[0]}")
        print(f"Tenant ID         : {row[1]}")
        print(f"Project ID        : {row[2]}")
        print(f"Dataset Code      : {row[3]}")
        print(f"Dataset Name      : {row[4]}")
        print(f"Dataset Role      : {row[5]}")
        print(f"Object Type       : {row[6]}")
        print(f"Layer             : {row[7]}")
        print(f"Status            : {row[8]}")

        # ================================================================
        # 3. Validate target dataset.
        # ================================================================

        # Confirm the dataset ID.
        if row[0] != TARGET_DATASET_ID:
            raise RuntimeError(
                "Unexpected target dataset ID."
            )

        # Confirm that this is a TARGET dataset.
        if row[5] != "TARGET":
            raise RuntimeError(
                "Target dataset role is not TARGET."
            )

        # Confirm that the dataset represents a table.
        if row[6] != "TABLE":
            raise RuntimeError(
                "Target dataset object type is not TABLE."
            )

        # Confirm that the dataset is active.
        if row[8] != "ACTIVE":
            raise RuntimeError(
                "Target dataset is not ACTIVE."
            )

        # ================================================================
        # 4. Display binding metadata.
        # ================================================================
        print()
        print("=" * 90)
        print("TARGET BINDING")
        print("=" * 90)

        print(f"Binding ID        : {row[9]}")
        print(f"Environment ID    : {row[10]}")
        print(f"Connection ID     : {row[11]}")
        print(f"Database          : {row[12]}")
        print(f"Schema            : {row[13]}")
        print(f"Object            : {row[14]}")
        print(f"Normalized Object : {row[15]}")
        print(f"Status            : {row[16]}")

        # ================================================================
        # 5. Validate target binding.
        # ================================================================

        # Confirm the binding ID.
        if row[9] != TARGET_BINDING_ID:
            raise RuntimeError(
                "Unexpected target binding ID."
            )

        # Confirm the environment.
        if row[10] != ENVIRONMENT_ID:
            raise RuntimeError(
                "Target binding environment does not match Environment 1."
            )

        # Confirm the target connection.
        if row[11] != TARGET_CONNECTION_ID:
            raise RuntimeError(
                "Target binding does not point to Connection 11."
            )

        # Confirm the physical database.
        if row[12] != TARGET_DATABASE:
            raise RuntimeError(
                "Target database does not match ingestion_metastore."
            )

        # Confirm the physical schema.
        if row[13] != TARGET_SCHEMA:
            raise RuntimeError(
                "Target schema does not match warehouse."
            )

        # Confirm the physical object.
        if row[14] != TARGET_OBJECT:
            raise RuntimeError(
                "Target object does not match customer_target."
            )

        # Confirm active status.
        if row[16] != "ACTIVE":
            raise RuntimeError(
                "Target binding is not ACTIVE."
            )

        # ================================================================
        # 6. Final verification result.
        # ================================================================
        print()
        print("=" * 90)
        print("TARGET BINDING VERIFICATION SUCCESSFUL")
        print("=" * 90)

        print("Target Dataset     : VERIFIED")
        print("Target Binding     : VERIFIED")
        print("Connection 11      : VERIFIED")
        print("Environment 1      : VERIFIED")
        print(
            "Physical Location  : "
            f"{TARGET_DATABASE}.{TARGET_SCHEMA}.{TARGET_OBJECT}"
        )
        print("Metadata Changes   : NONE")


# Execute the verification when this module is run directly.
if __name__ == "__main__":
    main()