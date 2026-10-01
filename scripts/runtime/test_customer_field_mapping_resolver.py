"""
Customer Field Mapping Resolver Test
=====================================

Purpose
-------
Validate that RuntimeFieldMappingResolver correctly resolves the
source-to-target field mappings for the Customer Full Load POC.

Test Metadata
-------------
Tenant ID        : 1
Mapping Version  : 2

Expected mappings:

    customer_id    -> customer_id
    customer_name  -> customer_name
    email          -> email
    city           -> city

IMPORTANT:
----------
This test is READ-ONLY.

It only reads metadata from the metadata store.
It does not connect to the source database.
It does not connect to the target database.
It does not modify metadata or business data.
"""

from app.runtime.field_mapping_resolver import RuntimeFieldMappingResolver


def main() -> None:
    """
    Resolve and validate Customer field mappings.
    """

    # -------------------------------------------------------------
    # These identifiers come from the existing Customer POC
    # metadata configuration.
    # -------------------------------------------------------------
    tenant_id = 1
    mapping_version_id = 2

    print("=" * 80)
    print("CUSTOMER FIELD MAPPING RESOLVER TEST")
    print("=" * 80)

    # -------------------------------------------------------------
    # Create the resolver.
    # -------------------------------------------------------------
    resolver = RuntimeFieldMappingResolver()

    # -------------------------------------------------------------
    # Resolve field mappings dynamically from metadata.
    # -------------------------------------------------------------
    field_mappings = resolver.resolve(
        mapping_version_id=mapping_version_id,
        tenant_id=tenant_id,
    )

    # -------------------------------------------------------------
    # Display the resolved mappings.
    # -------------------------------------------------------------
    print()
    print("Resolved Field Mappings:")
    print("-" * 80)

    for mapping in field_mappings:
        print(
            f"Ordinal {mapping.ordinal_no}: "
            f"{mapping.source_field_name} "
            f"-> "
            f"{mapping.target_field_name} "
            f"| Type={mapping.mapping_type_code} "
            f"| Source Field ID={mapping.source_field_id} "
            f"| Target Field ID={mapping.target_field_id}"
        )

    # -------------------------------------------------------------
    # Validate the number of mappings.
    # -------------------------------------------------------------
    expected_count = 4

    if len(field_mappings) != expected_count:
        raise AssertionError(
            "Expected "
            f"{expected_count} field mappings, "
            f"but received {len(field_mappings)}."
        )

    # -------------------------------------------------------------
    # Define the expected source-to-target relationships.
    #
    # These are validation expectations for the current POC.
    # The resolver itself does not hardcode these values.
    # -------------------------------------------------------------
    expected_mappings = [
        ("customer_id", "customer_id"),
        ("customer_name", "customer_name"),
        ("email", "email"),
        ("city", "city"),
    ]

    # -------------------------------------------------------------
    # Compare the resolved metadata with the expected POC
    # configuration.
    # -------------------------------------------------------------
    actual_mappings = [
        (
            mapping.source_field_name,
            mapping.target_field_name,
        )
        for mapping in field_mappings
    ]

    if actual_mappings != expected_mappings:
        raise AssertionError(
            "Resolved field mappings do not match the expected "
            f"Customer POC mappings.\n"
            f"Expected: {expected_mappings}\n"
            f"Actual:   {actual_mappings}"
        )

    # -------------------------------------------------------------
    # Validate that all mappings are DIRECT mappings for the
    # current Customer POC.
    # -------------------------------------------------------------
    if any(
        mapping.mapping_type_code != "DIRECT"
        for mapping in field_mappings
    ):
        raise AssertionError(
            "Expected all Customer POC field mappings to be DIRECT."
        )

    # -------------------------------------------------------------
    # Validate that mappings are ordered correctly.
    # -------------------------------------------------------------
    actual_ordinals = [
        mapping.ordinal_no
        for mapping in field_mappings
    ]

    expected_ordinals = [1, 2, 3, 4]

    if actual_ordinals != expected_ordinals:
        raise AssertionError(
            "Field mapping ordinals are incorrect.\n"
            f"Expected: {expected_ordinals}\n"
            f"Actual:   {actual_ordinals}"
        )

    print()
    print("Mapping Count Validation : PASSED")
    print("Source-to-Target Mapping : PASSED")
    print("Mapping Type Validation   : PASSED")
    print("Ordinal Validation        : PASSED")
    print()
    print("CUSTOMER FIELD MAPPING RESOLVER TEST PASSED")
    print("=" * 80)


if __name__ == "__main__":
    main()