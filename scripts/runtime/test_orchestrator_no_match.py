
"""Isolated test for a physical-table selection matching no tasks."""

from types import SimpleNamespace

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


class FakeMetadataResolver:
    def resolve_all(self, pipeline_version_id: int):
        return [
            SimpleNamespace(
                task=SimpleNamespace(
                    task_id=101,
                    task_code="TEST_TASK",
                    task_name="No Match Test",
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
    def __init__(self):
        self.connector_resolution_called = False

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
        self.connector_resolution_called = True
        raise AssertionError(
            "Connector resolution must not run for an excluded task."
        )


class FakeRunTracker:
    def __init__(self):
        self.task_started = False
        self.task_statuses = []
        self.pipeline_statuses = []

    def start_pipeline(
        self, pipeline_version_id, tenant_id, environment_id
    ):
        return 9001, 7001, "TEST_BATCH_9001"

    def start_task(
        self, run_id, tenant_id, project_id, task_id, mapping_version_id
    ):
        self.task_started = True
        raise AssertionError(
            "Task tracking must not start for an excluded task."
        )

    def finish_task(
        self, task_run_id, started, status_code, rows_written=0
    ):
        self.task_statuses.append(status_code)

    def finish_pipeline(self, run_id, status_code):
        self.pipeline_statuses.append(status_code)


def main() -> None:
    context_resolver = FakeContextResolver()
    tracker = FakeRunTracker()

    orchestrator = PipelineOrchestrator(
        metadata_resolver=FakeMetadataResolver(),
        context_resolver=context_resolver,
        run_tracker=tracker,
    )

    try:
        orchestrator.execute_pipeline(
            pipeline_version_id=1,
            tenant_id=1,
            environment_id=1,
            selected_source_tables=["missing_table"],
        )
    except LookupError as exc:
        assert "No configured tasks matched" in str(exc)
    else:
        raise AssertionError("Expected a no-match LookupError.")

    assert not context_resolver.connector_resolution_called
    assert not tracker.task_started
    assert tracker.task_statuses == []
    assert tracker.pipeline_statuses == ["FAILED"]

    print("No-match selection handling : PASSED")
    print("Connector resolution skipped: PASSED")
    print("Task tracking skipped       : PASSED")
    print("Pipeline marked FAILED     : PASSED")
    print("Database writes             : NONE")


if __name__ == "__main__":
    main()
