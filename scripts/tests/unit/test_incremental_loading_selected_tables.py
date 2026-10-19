"""Unit tests for selected-table incremental-load error scenarios."""

import unittest
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from incremental_loading.scripts import incremental_loading_selected_tables as cli


class TableSelectionTests(unittest.TestCase):
    def test_rejects_unknown_and_duplicate_table_names(self) -> None:
        available = ["customer", "department"]

        with self.assertRaisesRegex(ValueError, "not found"):
            cli.select_named_tables(["missing"], available)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            cli.select_named_tables(["customer", "customer"], available)

    def test_rejects_invalid_menu_numbers(self) -> None:
        available = ["customer", "department"]

        for selection in ("0", "3", "1,1", "1,x", ""):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    cli.select_table_numbers(selection, available)

    def test_prompt_eof_cancels_without_loading(self) -> None:
        with patch.object(cli, "input", side_effect=EOFError):
            output = StringIO()
            with redirect_stdout(output):
                selected = cli.prompt_for_tables(["customer"])

        self.assertEqual(selected, [])
        self.assertIn("cancelled", output.getvalue())


class MainErrorHandlingTests(unittest.TestCase):
    def make_source_connector(self, tables: list[str]) -> Mock:
        source = Mock()
        source.metadata = SimpleNamespace(database_name="source_db")
        source.list_tables.return_value = tables
        return source

    def test_source_connection_failure_is_reported(self) -> None:
        source = self.make_source_connector([])
        source.connect.side_effect = RuntimeError("source unavailable")
        resolver = Mock()
        resolver.resolve.return_value = source
        output = StringIO()

        with (
            patch.object(cli, "RuntimeConnectionResolver", return_value=resolver),
            redirect_stdout(output),
        ):
            result = cli.main(["--list-tables"])

        self.assertEqual(result, 1)
        self.assertIn("Unable to connect to or discover source tables", output.getvalue())
        self.assertIn("source unavailable", output.getvalue())

    def test_empty_source_schema_is_reported(self) -> None:
        source = self.make_source_connector([])
        resolver = Mock()
        resolver.resolve.return_value = source
        output = StringIO()

        with (
            patch.object(cli, "RuntimeConnectionResolver", return_value=resolver),
            redirect_stdout(output),
        ):
            result = cli.main(["--list-tables"])

        self.assertEqual(result, 1)
        self.assertIn("No source tables found", output.getvalue())

    def test_target_resolution_failure_is_reported(self) -> None:
        source = self.make_source_connector(["customer"])
        resolver = Mock()
        resolver.resolve.side_effect = [source, RuntimeError("target unavailable")]
        output = StringIO()

        with (
            patch.object(cli, "RuntimeConnectionResolver", return_value=resolver),
            patch.object(cli, "prompt_for_tables", return_value=["customer"]),
            redirect_stdout(output),
        ):
            result = cli.main([])

        self.assertEqual(result, 1)
        self.assertIn("Unable to resolve target connection", output.getvalue())
        self.assertIn("target unavailable", output.getvalue())

    def test_load_continues_after_a_table_fails(self) -> None:
        source = self.make_source_connector(["customer", "department"])
        resolver = Mock()
        resolver.resolve.side_effect = [source, Mock()]
        output = StringIO()

        with (
            patch.object(cli, "RuntimeConnectionResolver", return_value=resolver),
            patch.object(
                cli.multi_table_loader,
                "run_table",
                side_effect=[
                    (3, 3, None),
                    RuntimeError("unsupported source type"),
                ],
            ) as run_table,
            redirect_stdout(output),
        ):
            result = cli.main(["--tables", "customer", "department"])

        self.assertEqual(result, 1)
        self.assertEqual(run_table.call_count, 2)
        self.assertIn("Tables loaded successfully into target (1)", output.getvalue())
        self.assertIn("Failed table names", output.getvalue())
        self.assertIn("department", output.getvalue())
        self.assertIn("unsupported source type", output.getvalue())


if __name__ == "__main__":
    unittest.main()
