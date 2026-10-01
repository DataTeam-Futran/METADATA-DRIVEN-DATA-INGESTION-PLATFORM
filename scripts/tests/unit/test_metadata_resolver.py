from app.metadata.resolver import MetadataResolver


def main() -> None:
    print("=" * 80)
    print("METADATA RESOLVER TEST")
    print("=" * 80)

    mapping_version_id = 1

    resolver = MetadataResolver()

    print()
    print(
        f"Resolving mapping_version_id={mapping_version_id}..."
    )

    metadata = resolver.resolve(mapping_version_id)

    print()
    print("METADATA RESOLUTION SUCCESSFUL")
    print()

    print("LOAD")
    print(f"  Mapping Version : {metadata.load.mapping_version_id}")
    print(f"  Load Type       : {metadata.load.load_type}")
    print(f"  Batch Size      : {metadata.load.batch_size}")
    print(
        f"  Truncate        : "
        f"{metadata.load.truncate_before_load}"
    )

    print()
    print("SOURCE")
    print(f"  Source ID       : {metadata.source.source_id}")
    print(f"  Dataset         : {metadata.source.dataset_name}")
    print(f"  Database        : {metadata.source.database_name}")
    print(f"  Schema          : {metadata.source.schema_name}")
    print(f"  Object          : {metadata.source.object_name}")

    print()
    print("TARGET")
    print(f"  Target ID       : {metadata.target.target_id}")
    print(f"  Database        : {metadata.target.database_name}")
    print(f"  Schema          : {metadata.target.schema_name}")
    print(f"  Object          : {metadata.target.object_name}")

    print()
    print("FIELDS")

    for field in metadata.mapping_fields:
        transformation = ""

        if field.transformation_type:
            transformation = (
                f" [{field.transformation_type}]"
            )

        print(
            f"  {field.source_field_name}"
            f" -> "
            f"{field.target_field_name}"
            f" | {field.target_data_type}"
            f"{transformation}"
        )

    print()
    print("=" * 80)
    print("METADATA RESOLVER TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()