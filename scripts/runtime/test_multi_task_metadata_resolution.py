from app.runtime.metadata_resolver import RuntimeMetadataResolver


PIPELINE_VERSION_ID = 2


def main() -> None:
    resolver = RuntimeMetadataResolver()

    plans = resolver.resolve_all(PIPELINE_VERSION_ID)

    print(f"Pipeline version: {PIPELINE_VERSION_ID}")
    print(f"Tasks resolved: {len(plans)}")

    for plan in plans:
        print(
            f"Sequence={plan.task.sequence_no} | "
            f"Task ID={plan.task.task_id} | "
            f"Task={plan.task.task_name} | "
            f"Mapping version={plan.mapping.mapping_version_id} | "
            f"Source dataset={plan.mapping.primary_source_dataset_id} | "
            f"Target dataset={plan.mapping.target_dataset_id}"
        )

    assert plans, "Expected at least one task."
    assert len(plans) == len(
        sorted(plans, key=lambda p: (p.task.sequence_no, p.task.task_id))
    ), "Tasks are not in execution order."

    print("Metadata resolution test: PASSED")


if __name__ == "__main__":
    main()