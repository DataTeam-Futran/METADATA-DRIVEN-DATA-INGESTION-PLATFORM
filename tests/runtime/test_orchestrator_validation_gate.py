
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


class TestOrchestratorValidationGate(unittest.TestCase):

    def test_failed_validation_prevents_executor_execution(self):
        # Arrange: create the task and its mapping.
        task = SimpleNamespace(
            task_id=1,
            task_code="TEST_TASK",
            task_name="Test Task",
            task_type="FULL_LOAD",
            sequence_no=1,
            failure_policy="STOP",
            timeout_seconds=600,
            mapping_version_id=1,
        )

        mapping = SimpleNamespace(
            mapping_version_id=1,
            status_code="ACTIVE",
            source_dataset_id=1,
            target_dataset_id=2,
            load_type="FULL",
            load_strategy="TRUNCATE_INSERT",
        )


        source_object = SimpleNamespace(
            catalog_name="source_catalog",
            schema_name="source_schema",
            object_name="source_table",
        )

        target_object = SimpleNamespace(
            catalog_name="target_catalog",
            schema_name="target_schema",
            object_name="target_table",
        )


        # Include every plan attribute used by the orchestrator.
        plan = SimpleNamespace(
            task=task,
            mapping=mapping,
            pipeline_version_status="PUBLISHED",
            source_object=source_object,
            target_object=target_object,
        )

        metadata_resolver = Mock()
        metadata_resolver.resolve_all.return_value = [plan]

        context_resolver = Mock()
        context_resolver.resolve_objects_for_plan.return_value = (
            source_object,
            target_object,
        )
        context_resolver.resolve_for_plan.return_value = Mock()

        field_mapping_resolver = Mock()
        field_mapping_resolver.resolve.return_value = [
            SimpleNamespace(
                source_field_name="id",
                target_field_name="id",
                mapping_type_code="DIRECT",
                source_field_id=1,
                target_field_id=1,
            )
        ]

        validator = Mock()
        validator.validate.return_value = [
            SimpleNamespace(
                check_name="TARGET_COLUMNS",
                passed=False,
                message="A mapped target column is missing.",
            )
        ]

        tracker = Mock()
        tracker.start_pipeline.return_value = (100, 1, 200)
        tracker.start_task.return_value = (
            300,
            datetime.now(timezone.utc),
        )

        orchestrator = PipelineOrchestrator(
            metadata_resolver=metadata_resolver,
            context_resolver=context_resolver,
            field_mapping_resolver=field_mapping_resolver,
            pre_execution_validator=validator,
            run_tracker=tracker,
        )

        with patch(
            "app.runtime.pipeline_orchestrator.FullLoadExecutor"
        ) as executor_class:

            # Act: deliberately fail pre-execution validation.
            with self.assertRaisesRegex(
                RuntimeError,
                "Pre-execution validation failed",
            ):
                orchestrator.execute_pipeline(
                    pipeline_version_id=1,
                    tenant_id=1,
                    environment_id=1,
                )

            # The full-load executor must not start.
            executor_class.assert_not_called()

        # Verify failed execution is tracked.
        tracker.finish_task.assert_called_once()
        tracker.finish_pipeline.assert_called_once_with(
            run_id=100,
            status_code="FAILED",
        )

    def test_draft_metadata_is_blocked_before_pipeline_run_starts(self):
        task = SimpleNamespace(
            task_id=1,
            task_code="TEST_TASK",
            task_name="Test Task",
            mapping_version_id=1,
        )
        mapping = SimpleNamespace(
            mapping_version_id=1,
            status_code="DRAFT",
        )
        plan = SimpleNamespace(
            task=task,
            mapping=mapping,
            pipeline_version_status="DRAFT",
        )

        metadata_resolver = Mock()
        metadata_resolver.resolve_all.return_value = [plan]
        tracker = Mock()
        orchestrator = PipelineOrchestrator(
            metadata_resolver=metadata_resolver,
            run_tracker=tracker,
        )

        with patch(
            "app.runtime.pipeline_orchestrator.FullLoadExecutor"
        ) as executor_class:
            with self.assertRaisesRegex(
                PermissionError,
                "not PUBLISHED",
            ):
                orchestrator.execute_pipeline(
                    pipeline_version_id=1,
                    tenant_id=1,
                    environment_id=1,
                )

            executor_class.assert_not_called()

        tracker.start_pipeline.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
