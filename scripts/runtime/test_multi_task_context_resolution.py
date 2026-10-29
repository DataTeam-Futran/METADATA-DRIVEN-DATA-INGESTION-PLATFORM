"""
Multi-Task Runtime Context Resolution Test

Purpose
-------
Resolve every execution plan and build its runtime context.

This test does not execute data ingestion.
"""

from app.runtime.context_resolver import RuntimeExecutionContextResolver
from app.runtime.metadata_resolver import RuntimeMetadataResolver


PIPELINE_VERSION_ID = 2
TENANT_ID = 1
ENVIRONMENT_ID = 1


def main() -> None:
    print("=" * 80)
    print("MULTI-TASK CONTEXT RESOLUTION TEST")
    print("=" * 80)

    # Resolve metadata plans for the selected pipeline version.
    metadata_resolver = RuntimeMetadataResolver()
    plans = metadata_resolver.resolve_all(
        pipeline_version_id=PIPELINE_VERSION_ID
    )

    if not plans:
        raise RuntimeError(
            f"No execution plans found for pipeline version "
            f"{PIPELINE_VERSION_ID}."
        )

    # Create the context resolver.
    context_resolver = RuntimeExecutionContextResolver(
        metadata_resolver=metadata_resolver
    )

    print(f"Pipeline Version : {PIPELINE_VERSION_ID}")
    print(f"Plans Resolved   : {len(plans)}")
    print()

    # Resolve the context for each execution plan.
    for plan in plans:
        context = context_resolver.resolve_for_plan(
            execution_plan=plan,
            tenant_id=TENANT_ID,
            environment_id=ENVIRONMENT_ID,
        )

        print("-" * 80)
        print(f"Task ID          : {plan.task.task_id}")
        print(f"Task Name        : {plan.task.task_name}")
        print(f"Sequence Number  : {plan.task.sequence_no}")
        print(f"Mapping Version  : {plan.mapping.mapping_version_id}")
        print(
            "Source Dataset   : "
            f"{plan.mapping.primary_source_dataset_id}"
        )
        print(
            "Target Dataset   : "
            f"{plan.mapping.target_dataset_id}"
        )
        print(
            f"Source Connection: {context.source_object.connection_id}"
        )
        print(
            f"Target Connection: {context.target_object.connection_id}"
        )

    print()
    print("=" * 80)
    print("MULTI-TASK CONTEXT RESOLUTION TEST PASSED")
    print("=" * 80)
    print(f"Contexts Resolved: {len(plans)}")


if __name__ == "__main__":
    main()
