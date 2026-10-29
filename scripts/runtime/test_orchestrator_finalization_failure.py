
from types import SimpleNamespace
from unittest.mock import patch

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


class FakeMetadataResolver:
    def resolve_all(self, pipeline_version_id):
        mapping = SimpleNamespace(
            primary_source_dataset_id=301,
            target_dataset_id=401,
            mapping_version_id=201,
        )

        task = SimpleNamespace(
    task_id=101,
    task_code="TEST_TASK",
    task_name="Test Task",
    sequence_no=1,
)

        plan = SimpleNamespace(
            task=task,
            mapping=mapping,
        )

        return [plan]


class FakeContextResolver:
    def resolve_objects_for_plan(
        self, execution_plan, tenant_id, environment_id
    ):
        return (
            SimpleNamespace(
                connection_id=1,
                catalog_name="test_source",
                schema_name="public",
                object_name="source_table",
            ),
            SimpleNamespace(
                connection_id=2,
                catalog_name="test_target",
                schema_name="public",
                object_name="target_table",
            ),
        )

    def resolve_for_plan(
        self, execution_plan, tenant_id, environment_id
    ):
        return SimpleNamespace(
            source_connector=object(),
            target_connector=object(),
            source_object=SimpleNamespace(
                connection_id=1,
                catalog_name="test_source",
                schema_name="public",
                object_name="source_table",
            ),
            target_object=SimpleNamespace(
                connection_id=2,
                catalog_name="test_target",
                schema_name="public",
                object_name="target_table",
            ),
        )


class FakeMappingResolver:
    def resolve(self, mapping_version_id, tenant_id):
        return []


class FakeValidator:
    def validate(self, context, field_mappings=None):
        return []


class FakeRunTracker:
    def __init__(self, fail_pipeline_finalization=False):
        self.fail_pipeline_finalization = fail_pipeline_finalization
        self.task_statuses = []
        self.pipeline_statuses = []

    def start_pipeline(self, **kwargs):
        return 9001, 7001, "TEST_BATCH_9001"

    def start_task(self, **kwargs):
       from datetime import datetime, timezone

       return 9101, datetime.now(timezone.utc)

    def finish_task(self, **kwargs):
       self.task_statuses.append(kwargs.get("status_code"))

    def finish_pipeline(self, **kwargs):
        status = kwargs.get("status_code")
        self.pipeline_statuses.append(status)

        if self.fail_pipeline_finalization:
            raise RuntimeError("Simulated pipeline finalization failure")


def main():
    tracker = FakeRunTracker(fail_pipeline_finalization=True)

    orchestrator = PipelineOrchestrator(
        metadata_resolver=FakeMetadataResolver(),
        context_resolver=FakeContextResolver(),
        field_mapping_resolver=FakeMappingResolver(),
        pre_execution_validator=FakeValidator(),
        run_tracker=tracker,
    )

    try:
        with patch(
            "app.runtime.pipeline_orchestrator.FullLoadExecutor"
        ) as executor_class:
            executor_class.return_value.execute.side_effect = RuntimeError(
                "Simulated original task failure"
            )

            orchestrator.execute_pipeline(
                pipeline_version_id=1,
                tenant_id=1,
                environment_id=1,
            )

    except RuntimeError as exc:
        message = str(exc)

        if message == "Simulated original task failure":
            print("Original task error preserved: PASSED")
        else:
            print(f"Unexpected final exception: {message}")
            raise AssertionError(
                "The original task error was replaced by a finalization error"
            ) from exc
    else:
        raise AssertionError("Expected the original task failure")

    assert tracker.task_statuses == ["FAILED"], tracker.task_statuses
    print("Task marked FAILED: PASSED")

    assert tracker.pipeline_statuses == ["FAILED"], tracker.pipeline_statuses
    print("Pipeline finalization attempted: PASSED")

    print("Real data movement: NONE")
    print("Real database writes: NONE")


if __name__ == "__main__":
    main()
