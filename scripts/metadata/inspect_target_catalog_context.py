"""
Target Catalog Context Inspection

Purpose:
    Inspect the existing target-side catalog metadata model before creating
    the Customer target dataset and target binding.

Why this script exists:
    We already have a valid target connection (Connection 11).
    Before creating new catalog metadata, we verify that the target catalog
    tables and existing records support the intended Tenant 1 / Project 1
    target registration.

Important:
    This script is READ-ONLY.
    It does not insert, update, or delete any metadata.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC target identifiers
# ---------------------------------------------------------------------------
# Connection 11 is the existing dynamic target connection.
TARGET_CONNECTION_ID = 11

# Tenant and project already used by the Customer source POC.
TENANT_ID = 1
PROJECT_ID = 1


def main() -> None:
    """Inspect the target catalog context."""

    # Open a connection to the metadata/control database.
    with get_metastore_connection() as connection:

        # ================================================================
        # 1. TARGET CONNECTION
        # ================================================================
        print("=" * 90)
        print("1. TARGET CONNECTION")
        print("=" * 90)

        connection_query = """
            SELECT
                cp.connection_id,
                cp.tenant_id,
                cp.system_id,
                cp.environment_id,
                cp.connector_version_id,
                cp.credential_id,
                cp.connection_role_code,
                cp.connection_name,
                cp.host_name,
                cp.port_no,
                cp.database_name,
                cp.status_code
            FROM conn.connection_profile AS cp
            WHERE cp.connection_id = %s;
        """

        # Execute the target connection lookup.
        with connection.cursor() as cursor:
            cursor.execute(
                connection_query,
                (TARGET_CONNECTION_ID,),
            )

            # Read the target connection metadata.
            target_connection = cursor.fetchone()

        # Stop if Connection 11 does not exist.
        if target_connection is None:
            raise LookupError(
                f"Target Connection {TARGET_CONNECTION_ID} was not found."
            )

        # Display safe target metadata.
        print(f"Connection ID       : {target_connection[0]}")
        print(f"Tenant ID            : {target_connection[1]}")
        print(f"System ID            : {target_connection[2]}")
        print(f"Environment ID       : {target_connection[3]}")
        print(f"Connector Version    : {target_connection[4]}")
        print(f"Credential ID        : {target_connection[5]}")
        print(f"Role                 : {target_connection[6]}")
        print(f"Connection Name      : {target_connection[7]}")
        print(f"Host                 : {target_connection[8]}")
        print(f"Port                 : {target_connection[9]}")
        print(f"Database             : {target_connection[10]}")
        print(f"Status               : {target_connection[11]}")

        # Verify that this is actually a target connection.
        if target_connection[6] not in ("TARGET", "BOTH"):
            raise RuntimeError(
                "Connection 11 is not configured as TARGET or BOTH."
            )

        # ================================================================
        # 2. TARGET DATASETS FOR TENANT 1 / PROJECT 1
        # ================================================================
        print()
        print("=" * 90)
        print("2. EXISTING TARGET DATASETS")
        print("=" * 90)

        dataset_query = """
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
            WHERE tenant_id = %s
              AND project_id = %s
              AND dataset_role_code = 'TARGET'
            ORDER BY dataset_id;
        """

        # Execute the target dataset lookup.
        with connection.cursor() as cursor:
            cursor.execute(
                dataset_query,
                (TENANT_ID, PROJECT_ID),
            )

            # Fetch all target datasets for this tenant/project.
            target_datasets = cursor.fetchall()

        # Show existing target datasets.
        if not target_datasets:
            print("No target dataset currently exists for Tenant 1 / Project 1.")
        else:
            for dataset in target_datasets:
                print(
                    f"Dataset ID={dataset[0]} | "
                    f"Code={dataset[3]} | "
                    f"Name={dataset[4]} | "
                    f"Object={dataset[5]} | "
                    f"Role={dataset[6]} | "
                    f"Layer={dataset[7]} | "
                    f"Status={dataset[8]}"
                )

        # ================================================================
        # 3. TARGET BINDINGS FOR CONNECTION 11
        # ================================================================
        print()
        print("=" * 90)
        print("3. EXISTING TARGET BINDINGS")
        print("=" * 90)

        binding_query = """
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
            WHERE tenant_id = %s
              AND connection_id = %s
            ORDER BY dataset_binding_id;
        """

        # Execute the target binding lookup.
        with connection.cursor() as cursor:
            cursor.execute(
                binding_query,
                (TENANT_ID, TARGET_CONNECTION_ID),
            )

            # Fetch existing bindings for Connection 11.
            target_bindings = cursor.fetchall()

        # Display the existing target bindings.
        if not target_bindings:
            print("No target binding currently exists for Connection 11.")
        else:
            for binding in target_bindings:
                print(
                    f"Binding ID={binding[0]} | "
                    f"Dataset ID={binding[2]} | "
                    f"Environment={binding[3]} | "
                    f"Database={binding[5]} | "
                    f"Schema={binding[6]} | "
                    f"Object={binding[7]} | "
                    f"Status={binding[9]}"
                )

        # ================================================================
        # 4. FINAL RESULT
        # ================================================================
        print()
        print("=" * 90)
        print("TARGET CATALOG CONTEXT INSPECTION COMPLETE")
        print("=" * 90)
        print("Metadata Changes : NONE")


# Execute the inspection when this module is run directly.
if __name__ == "__main__":
    main()