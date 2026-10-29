
"""
Isolated orchestrator connector-failure test.

Purpose:
- Simulate a connector-resolution failure.
- Verify task and pipeline failure tracking.
- Avoid database connections and data ingestion.

All dependencies are controlled test doubles.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


class FakeMetadataResolver:
    """Return a synthetic execution plan without database access."""

    def resolve_all(self, pipeline_version_id: int):
        task = SimpleNamespace(
            task_id=101,
            task_code="TEST_TASK",
            task_name="Isolated Failure Test",
            sequence_no=1,
        )

        mapping = SimpleNamespace(
            mapping_version_id=201,
            primary_source_dataset_id=301,
            target_dataset_id=401,
        )

        return [
            SimpleNamespace(
                task=task,
                mapping=mapping,
            )
        ]


class FakeContextResolver:
    """Resolve synthetic objects, then simulate connector failure."""

    def resolve_objects_for_plan(
        self,
        execution_plan,
        tenant_id: int,
        environment_id: int,
    ):
        source = SimpleNamespace(
            catalog_name="test_source",
            schema_name="public",
            object_name="source_table",
        )

        target = SimpleNamespace(
            catalog_name="test_target",
            schema_name="public",
            object_name="target_table",
        )

        return source, target

    def resolve_for_plan(
        self,
        execution_plan,
        tenant_id: int,
        environment_id: int,
    ):
        raise RuntimeError("Simulated connector-resolution failure")


class FakeRunTracker:
    """Capture run-tracking calls without writing to the database."""

    def __init__(self):
        self.task_statuses = []
        self.pipeline_statuses = []

    def start_pipeline(
        self,
        pipeline_version_id: int,
        tenant_id: int,
        environment_id: int,
    ):
        return 9001, 7001, "TEST_BATCH_9001"

    def start_task(
        self,
        run_id: int,
        tenant_id: int,
        project_id: int,
        task_id: int,
        mapping_version_id: int | None,
    ):
        return 9101, datetime.now(timezone.utc)

    def finish_task(
        self,
        task_run_id: int,
        started: datetime,
        status_code: str,
        rows_written: int = 0,
    ):
        self.task_statuses.append(
            {
                "task_run_id": task_run_id,
                "status_code": status_code,
                "rows_written": rows_written,
            }
        )

    def finish_pipeline(
        self,
        run_id: int,
        status_code: str,
    ):
        self.pipeline_statuses.append(
            {
                "run_id": run_id,
                "status_code": status_code,
            }
        )


def main() -> None:
    tracker = FakeRunTracker()

    orchestrator = PipelineOrchestrator(
        metadata_resolver=FakeMetadataResolver(),
        context_resolver=FakeContextResolver(),
        run_tracker=tracker,
    )

    try:
        orchestrator.execute_pipeline(
            pipeline_version_id=1,
            tenant_id=1,
            environment_id=1,
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "Simulated connector-resolution failure"
        )
    else:
        raise AssertionError(
            "Expected connector-resolution failure was not raised."
        )

    assert len(tracker.task_statuses) == 1
    assert tracker.task_statuses[0]["status_code"] == "FAILED"
    assert tracker.task_statuses[0]["rows_written"] == 0

    assert len(tracker.pipeline_statuses) == 1
    assert tracker.pipeline_statuses[0]["status_code"] == "FAILED"

    print("Connector-resolution failure: PASSED")
    print("Task failure tracking       : PASSED")
    print("Pipeline failure tracking   : PASSED")
    print("Database writes             : NONE")


if __name__ == "__main__":
    main()
