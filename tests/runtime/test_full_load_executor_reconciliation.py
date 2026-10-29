from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.core.exceptions import (
    ConnectionResolutionError,
    DataQualityError,
    NoSourceDataError,
    SchemaValidationError,
    TargetWriteError,
)
from app.runtime.full_load_executor import FullLoadExecutor


def build_test_context(target_row_count=2):
    """Build a runtime context with mocked source and target connectors."""

    source = Mock()
    target = Mock()

    source.read_batches.return_value = iter([
        [("A",)],
        [("B",)],
    ])

    target.write_batch.side_effect = lambda **kwargs: len(kwargs["rows"])
    target.count_rows.return_value = target_row_count

    context = SimpleNamespace(
        execution_plan=SimpleNamespace(
            mapping=SimpleNamespace(
                load_type_code="FULL",
                load_strategy_code="TRUNCATE_INSERT",
            ),
            load_config=SimpleNamespace(
                batch_size=1,
                truncate_before_load=True,
            ),
            target_config=SimpleNamespace(),
        ),
        source_object=SimpleNamespace(
            schema_name="public",
            object_name="source_table",
        ),
        target_object=SimpleNamespace(
            schema_name="warehouse",
            object_name="target_table",
        ),
        source_connector=source,
        target_connector=target,
    )

    field_mappings = [
        SimpleNamespace(
            ordinal_no=1,
            source_field_name="customer_name",
            target_field_name="customer_name",
            mapping_type_code="DIRECT",
            mapping_field_id=1,
        )
    ]

    return context, field_mappings, source, target


class TestFullLoadReconciliation(unittest.TestCase):

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_matching_row_counts_allow_success(self, _validate_schema):
        context, mappings, source, target = build_test_context(2)

        result = FullLoadExecutor().execute(context, mappings)

        self.assertEqual(result, 2)
        target.count_rows.assert_called_once_with(
            schema_name="warehouse",
            table_name="target_table",
        )
        target.commit.assert_called_once()
        target.rollback.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_each_source_batch_is_written_exactly_once(
        self, _validate_schema
    ):
        context, mappings, source, target = build_test_context(3)

        source.read_batches.return_value = iter([
            [("A",)],
            [("B",)],
            [("C",)],
        ])

        result = FullLoadExecutor().execute(context, mappings)

        self.assertEqual(result, 3)
        self.assertEqual(target.write_batch.call_count, 3)

        written_batches = [
            call.kwargs["rows"]
            for call in target.write_batch.call_args_list
        ]

        self.assertEqual(
            written_batches,
            [[("A",)], [("B",)], [("C",)]],
        )
        target.count_rows.assert_called_once_with(
            schema_name="warehouse",
            table_name="target_table",
        )
        target.commit.assert_called_once()
        target.rollback.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_row_count_mismatch_rolls_back(self, _validate_schema):
        context, mappings, source, target = build_test_context(1)

        with self.assertRaises(DataQualityError):
            FullLoadExecutor().execute(context, mappings)

        target.count_rows.assert_called_once()
        target.rollback.assert_called_once()
        target.commit.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_count_query_failure_rolls_back(self, _validate_schema):
        context, mappings, source, target = build_test_context(2)
        target.count_rows.side_effect = RuntimeError(
            "Simulated row-count query failure"
        )

        with self.assertRaises(TargetWriteError):
            FullLoadExecutor().execute(context, mappings)

        target.rollback.assert_called_once()
        target.commit.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_empty_source_does_not_truncate_target(
        self, _validate_schema
    ):
        context, mappings, source, target = build_test_context(0)
        source.read_batches.return_value = iter([])

        with self.assertRaises(NoSourceDataError):
            FullLoadExecutor().execute(context, mappings)

        target.begin_transaction.assert_not_called()
        target.truncate_table.assert_not_called()
        target.count_rows.assert_not_called()
        target.commit.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_truncate_failure_rolls_back(self, _validate_schema):
        context, mappings, source, target = build_test_context(2)
        target.truncate_table.side_effect = RuntimeError(
            "Simulated target truncate failure"
        )

        with self.assertRaises(TargetWriteError):
            FullLoadExecutor().execute(context, mappings)

        target.begin_transaction.assert_called_once()
        target.truncate_table.assert_called_once()
        target.write_batch.assert_not_called()
        target.rollback.assert_called_once()
        target.commit.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_batch_write_failure_rolls_back(self, _validate_schema):
        context, mappings, source, target = build_test_context(2)
        target.write_batch.side_effect = RuntimeError(
            "Simulated target batch-write failure"
        )

        with self.assertRaises(TargetWriteError):
            FullLoadExecutor().execute(context, mappings)

        target.truncate_table.assert_called_once()
        target.write_batch.assert_called_once()
        target.rollback.assert_called_once()
        target.commit.assert_not_called()

    @patch.object(
        FullLoadExecutor,
        "_validate_physical_schema",
        return_value=None,
    )
    def test_target_connection_failure_closes_source(
        self, _validate_schema
    ):
        context, mappings, source, target = build_test_context(2)

        target.connect.side_effect = RuntimeError(
            "Simulated target connection failure"
        )

        with self.assertRaises(ConnectionResolutionError):
            FullLoadExecutor().execute(context, mappings)

        source.connect.assert_called_once()
        source.close.assert_called_once()
        target.close.assert_not_called()
        target.begin_transaction.assert_not_called()
        target.truncate_table.assert_not_called()


    
    def test_datatype_mismatch_prevents_target_truncate_and_write(self):
        context, mappings, source, target = build_test_context(2)

        # Simulate the physical-schema validator detecting FL-010.
        with patch.object(
            FullLoadExecutor,
            "_validate_physical_schema",
            side_effect=SchemaValidationError(
                "Source datatype text is incompatible with target datatype int."
            ),
        ):
            with self.assertRaises(SchemaValidationError):
                FullLoadExecutor().execute(context, mappings)

        # The executor must stop before modifying the target.
        target.begin_transaction.assert_not_called()
        target.truncate_table.assert_not_called()
        target.write_batch.assert_not_called()
        target.commit.assert_not_called()

        # Source and target connections should still be cleaned up.
        source.close.assert_called_once()
        target.close.assert_called_once()

    
if __name__ == "__main__":
    unittest.main()
