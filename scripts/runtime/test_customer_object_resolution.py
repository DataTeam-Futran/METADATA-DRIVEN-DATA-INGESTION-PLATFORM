"""
Customer Runtime Object Resolution Test

Purpose
-------
Validates that the runtime object resolver can dynamically resolve:

    Source Dataset 7
        -> Connection 1
        -> demo_source_db.public.customer

    Target Dataset 8
        -> Connection 11
        -> ingestion_metastore.warehouse.customer_target

This test is READ ONLY.
"""

from app.runtime.object_resolver import RuntimeObjectResolver


def main() -> None:
    """
    Execute the Customer source/target object resolution test.
    """

    # Customer POC metadata identifiers.
    tenant_id = 1
    environment_id = 1

    # Source logical dataset created during metadata discovery.
    source_dataset_id = 7

    # Target logical dataset created for the full-load POC.
    target_dataset_id = 8

    # Create the resolver that reads physical object metadata.
    resolver = RuntimeObjectResolver()

    print("=" * 100)
    print("CUSTOMER RUNTIME OBJECT RESOLUTION")
    print("=" * 100)

    # Resolve the source dataset to its physical object.
    source_object = resolver.resolve(
        dataset_id=source_dataset_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    print()
    print("SOURCE OBJECT")
    print("-" * 100)
    print(f"Dataset ID              : {source_object.dataset_id}")
    print(f"Dataset Binding ID      : {source_object.dataset_binding_id}")
    print(f"Connection ID           : {source_object.connection_id}")
    print(f"Dataset Code            : {source_object.dataset_code}")
    print(f"Catalog                 : {source_object.catalog_name}")
    print(f"Schema                  : {source_object.schema_name}")
    print(f"Object                  : {source_object.object_name}")
    print(f"Normalized Object       : {source_object.object_name_normalized}")

    # Resolve the target dataset to its physical object.
    target_object = resolver.resolve(
        dataset_id=target_dataset_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    print()
    print("TARGET OBJECT")
    print("-" * 100)
    print(f"Dataset ID              : {target_object.dataset_id}")
    print(f"Dataset Binding ID      : {target_object.dataset_binding_id}")
    print(f"Connection ID           : {target_object.connection_id}")
    print(f"Dataset Code            : {target_object.dataset_code}")
    print(f"Catalog                 : {target_object.catalog_name}")
    print(f"Schema                  : {target_object.schema_name}")
    print(f"Object                  : {target_object.object_name}")
    print(f"Normalized Object       : {target_object.object_name_normalized}")

    # Validate the source metadata against the known Customer POC metadata.
    #
    # These assertions verify that the resolver returned the expected
    # metadata without hardcoding those physical values inside the resolver.
    assert source_object.connection_id == 1
    assert source_object.catalog_name == "demo_source_db"
    assert source_object.schema_name == "public"
    assert source_object.object_name == "customer"

    # Validate the target metadata against the known Customer POC metadata.
    assert target_object.connection_id == 11
    assert target_object.catalog_name == "ingestion_metastore"
    assert target_object.schema_name == "warehouse"
    assert target_object.object_name == "customer_target"

    print()
    print("=" * 100)
    print("RUNTIME OBJECT RESOLUTION PASSED")
    print("=" * 100)
    print("Source physical object : demo_source_db.public.customer")
    print("Target physical object : ingestion_metastore.warehouse.customer_target")
    print("Operation              : READ ONLY")
    print("Metadata modified      : NO")
    print("=" * 100)


if __name__ == "__main__":
    # Run the test only when this file is executed as a module/script.
    main()