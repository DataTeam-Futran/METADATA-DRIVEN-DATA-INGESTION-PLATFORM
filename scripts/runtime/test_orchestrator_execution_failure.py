
"""
Isolated orchestrator execution-failure test.

Simulates a successful context resolution followed by an executor failure.
No database connections or real data movement are performed.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


class FakeMetadataResolver:
    def resolve_all(self, pipeline_version_id: int):
        return [
            SimpleNamespace(
                task=SimpleNamespace(
                    task_id=101,
                    task_code="TEST_TASK",
                    task_name="Execution Failure Test",
                    sequence_no=1,
                ),
                mapping=SimpleNamespace(
                    mapping_version_id=201,
                    primary_source_dataset_id=301,
                    target_dataset_id=401,
                ),
            )
        ]


class FakeContextResolver:
    def resolve_objects_for_plan(
        self, execution_plan, tenant_id, environment_id
    ):
        return (
            SimpleNamespace(
                catalog_name="test_source",
                schema_name="public",
                object_name="source_table",
            ),
            SimpleNamespace(
                catalog_name="test_target",
                schema_name="public",
                object_name="target_table",
            ),
        )

    def resolve_for_plan(
        self, execution_plan, tenant_id, environment_id
    ):
        return SimpleNamespace(
            source_object=SimpleNamespace(
                catalog_name="test_source",
                schema_name="public",
                object_name="source_table",
            ),
            target_object=SimpleNamespace(
                catalog_name="test_target",
                schema_name="public",
                object_name="target_table",
            ),
        )


class FakeFieldMappingResolver:
    def resolve(self, mapping_version_id: int, tenant_id: int):
        return [SimpleNamespace(source_column="id", target_column="id")]


class FakeValidator:
    def validate(self, context, field_mappings):
        return [
            SimpleNamespace(
                passed=True,
                check_name="FAKE_VALIDATION",
                message="Synthetic validation passed",
            )
        ]


class FakeRunTracker:
    def __init__(self):
        self.task_statuses = []
        self.pipeline_statuses = []

    def start_pipeline(
        self, pipeline_version_id, tenant_id, environment_id
    ):
        return 9001, 7001, "TEST_BATCH_9001"

    def start_task(
        self, run_id, tenant_id, project_id, task_id, mapping_version_id
    ):
        return 9101, datetime.now(timezone.utc)

    def finish_task(
        self, task_run_id, started, status_code, rows_written=0
    ):
        self.task_statuses.append((status_code, rows_written))

    def finish_pipeline(self, run_id, status_code):
        self.pipeline_statuses.append(status_code)


def main() -> None:
    tracker = FakeRunTracker()

    orchestrator = PipelineOrchestrator(
        metadata_resolver=FakeMetadataResolver(),
        context_resolver=FakeContextResolver(),
        field_mapping_resolver=FakeFieldMappingResolver(),
        pre_execution_validator=FakeValidator(),
        run_tracker=tracker,
    )

    # Replace the real executor with a controlled failure.
    with patch(
        "app.runtime.pipeline_orchestrator.FullLoadExecutor"
    ) as executor_class:
        executor_class.return_value.execute.side_effect = RuntimeError(
            "Simulated executor failure"
        )

        try:
            orchestrator.execute_pipeline(
                pipeline_version_id=1,
                tenant_id=1,
                environment_id=1,
            )
        except RuntimeError as exc:
            assert str(exc) == "Simulated executor failure"
        else:
            raise AssertionError(
                "Expected executor failure was not raised."
            )

    assert tracker.task_statuses == [("FAILED", 0)]
    assert tracker.pipeline_statuses == ["FAILED"]

    print("Executor failure propagation : PASSED")
    print("Task failure tracking        : PASSED")
    print("Pipeline failure tracking    : PASSED")
    print("Real data movement           : NONE")


if __name__ == "__main__":
    main()
