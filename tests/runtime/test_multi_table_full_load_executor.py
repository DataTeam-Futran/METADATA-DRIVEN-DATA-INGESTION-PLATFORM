from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

from app.runtime.multi_table_full_load_executor import (
    MultiTableFullLoadExecutor,
)
from app.runtime.selective_table_full_load_executor import (
    parse_table_selection,
    render_discovery_report,
    render_selected_tables,
    render_selective_report,
)


class FakeConnector:
    def __init__(
        self,
        tables: list[str] | None = None,
        rows: dict[str, list[tuple[Any, ...]]] | None = None,
        primary_keys: dict[str, list[str]] | None = None,
    ) -> None:
        self.tables = tables or []
        self.rows = rows or {}
        self.primary_keys = primary_keys or {}
        self.metadata = SimpleNamespace(
            database_name="test_database",
            connection_name="test_connection",
            connector_code="POSTGRESQL_CONNECTOR",
        )
        self.target_rows: dict[str, list[tuple[Any, ...]]] = {}
        self.column_metadata = [
            {
                "column_name": "id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
            },
            {
                "column_name": "value",
                "data_type": "text",
                "ordinal_position": 2,
                "is_nullable": "YES",
            },
        ]
        self.added_columns: list[str] = []
        self.dropped_columns: list[str] = []
        self.fail_drop_column: str | None = None
        self.connected = False
        self.schema_created = False
        self.rollback_count = 0
        self.committed = 0
        self._transaction_snapshot: dict[str, list[tuple[Any, ...]]] | None = None
        self._column_snapshot: list[dict[str, Any]] | None = None

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def list_tables(self, schema_name: str) -> list[str]:
        return self.tables

    def list_columns(
        self,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        return list(self.column_metadata)

    def read_batches(
        self,
        query: str,
        batch_size: int,
    ):
        if "information_schema.table_constraints" in query:
            table_name = next(
                (name for name in self.tables if f"'{name}'" in query),
                None,
            )
            yield [(key,) for key in self.primary_keys.get(table_name or "", [])]
            return

        table_name = next(
            (name for name in self.tables if f'"{name}"' in query),
            None,
        )
        if table_name == "broken":
            raise RuntimeError("simulated source read failure")
        rows = self.rows.get(table_name or "", [])
        for offset in range(0, len(rows), batch_size):
            yield rows[offset:offset + batch_size]

    def count_rows(self, schema_name: str, table_name: str) -> int:
        return len(self.rows.get(table_name, [])) if not self.target_rows else len(
            self.target_rows.get(table_name, [])
        )

    def schema_exists(self, schema_name: str) -> bool:
        return self.schema_created

    def create_schema(self, schema_name: str) -> None:
        self.schema_created = True

    def table_exists(self, schema_name: str, table_name: str) -> bool:
        return table_name in self.target_rows

    def create_table(
        self,
        schema_name: str,
        table_name: str,
        columns: list[dict[str, Any]],
    ) -> None:
        self.target_rows[table_name] = []
        self.column_metadata = list(columns)

    def add_column(
        self,
        schema_name: str,
        table_name: str,
        column: dict[str, Any],
    ) -> None:
        self.column_metadata.append(dict(column))
        self.added_columns.append(column["column_name"])
        if table_name in self.target_rows:
            self.target_rows[table_name] = [
                row + (None,) for row in self.target_rows[table_name]
            ]

    def drop_column(
        self,
        schema_name: str,
        table_name: str,
        column_name: str,
    ) -> None:
        column_index = next(
            index
            for index, metadata in enumerate(self.column_metadata)
            if metadata["column_name"] == column_name
        )
        self.column_metadata.pop(column_index)
        if table_name in self.target_rows:
            self.target_rows[table_name] = [
                row[:column_index] + row[column_index + 1:]
                for row in self.target_rows[table_name]
            ]
        self.dropped_columns.append(column_name)
        if column_name == self.fail_drop_column:
            raise RuntimeError("simulated target column drop failure")

    def begin_transaction(self) -> None:
        self._transaction_snapshot = {
            name: list(rows) for name, rows in self.target_rows.items()
        }
        self._column_snapshot = list(self.column_metadata)

    def truncate_table(self, target_schema: str, target_table: str) -> None:
        self.target_rows[target_table] = []

    def write_batch(
        self,
        target_schema: str,
        target_table: str,
        column_names: list[str],
        rows: list[tuple[Any, ...]],
    ) -> int:
        target_column_positions = {
            column["column_name"]: index
            for index, column in enumerate(self.column_metadata)
        }
        for row in rows:
            target_row: list[Any] = [None] * len(self.column_metadata)
            for name, value in zip(column_names, row):
                target_row[target_column_positions[name]] = value
            self.target_rows[target_table].append(tuple(target_row))
        return len(rows)

    def commit(self) -> None:
        self.committed += 1
        self._transaction_snapshot = None
        self._column_snapshot = None

    def rollback(self) -> None:
        self.rollback_count += 1
        if self._transaction_snapshot is not None:
            self.target_rows = self._transaction_snapshot
            self._transaction_snapshot = None
        if self._column_snapshot is not None:
            self.column_metadata = self._column_snapshot
            self._column_snapshot = None


class MultiTableFullLoadExecutorTests(unittest.TestCase):
    def _executor(
        self,
        source: FakeConnector,
        target: FakeConnector,
    ) -> MultiTableFullLoadExecutor:
        resolver = Mock()
        resolver.resolve.side_effect = {1: source, 11: target}.get
        return MultiTableFullLoadExecutor(connection_resolver=resolver)

    def test_prepare_target_tables_creates_schema_without_loading_data(self) -> None:
        source = FakeConnector(tables=["accounts"], rows={"accounts": [(1, "one")]})
        target = FakeConnector()
        executor = self._executor(source, target)

        preparations = executor.prepare_target_tables(
            "src",
            "dst",
            ["accounts"],
        )

        self.assertEqual(len(preparations), 1)
        self.assertEqual(
            preparations[0].schema_validation_status,
            "Match",
        )
        self.assertEqual(
            preparations[0].load_compatibility_status,
            "Compatible",
        )
        self.assertIsNone(preparations[0].error_details)
        self.assertEqual(target.target_rows["accounts"], [])
        self.assertEqual(target.committed, 2)
        self.assertFalse(source.connected)
        self.assertFalse(target.connected)

    def test_discovers_and_loads_all_tables_with_primary_keys(self) -> None:
        source = FakeConnector(
            tables=["accounts", "events"],
            rows={
                "accounts": [(1, "one")],
                "events": [(2, "two"), (3, "three")],
            },
            primary_keys={"accounts": ["id"], "events": ["id"]},
        )
        target = FakeConnector()

        executor = self._executor(source, target)
        with self.assertLogs(
            "app.runtime.multi_table_full_load_executor",
            level="INFO",
        ) as captured:
            summary = executor.execute("src", "dst")

        self.assertEqual(summary.succeeded, 2)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(summary.total_rows_extracted, 3)
        self.assertEqual(target.target_rows, source.rows)
        self.assertEqual(
            [table.schema_validation_status for table in summary.tables],
            ["Match", "Match"],
        )
        self.assertEqual(
            [table.load_compatibility_status for table in summary.tables],
            ["Compatible", "Compatible"],
        )
        self.assertEqual(
            [table.primary_keys for table in summary.tables],
            [["id"], ["id"]],
        )
        self.assertEqual(summary.discovered_table_count, 2)
        self.assertEqual(
            summary.tables[0].column_mappings,
            [
                {
                    "source_column": "id",
                    "target_column": "id",
                    "data_type": "integer",
                    "ordinal_position": "1",
                },
                {
                    "source_column": "value",
                    "target_column": "value",
                    "data_type": "text",
                    "ordinal_position": "2",
                },
            ],
        )
        report = summary.render_report()
        self.assertIn("SOURCE TABLE DISCOVERY (2 tables)", report)
        self.assertIn("| # | Source Schema | Discovered Table |", report)
        self.assertIn("| 1 | src           | accounts         |", report)
        self.assertIn("TARGET TABLES LOADED (2 tables)", report)
        self.assertIn("| # | Target Schema | Loaded Table |", report)
        self.assertIn("| 1 | dst           | accounts     |", report)
        self.assertIn("| Role   | Database      | Schema | Connection      |", report)
        self.assertNotIn("Connection ID", report)
        self.assertNotIn("DYNAMIC COLUMN MAPPINGS", report)
        self.assertNotIn("FULL LOAD RESULTS", report)
        self.assertNotIn("Source Column", report)
        self.assertIn("| Metric                     | Value", report)
        self.assertIn("| Tables loaded successfully | 2", report)
        self.assertIn("TABLE EXECUTION STATUS", report)
        status_section = report.split(
            "TABLE EXECUTION STATUS", maxsplit=1
        )[1].split("TABLE EXECUTION DETAILS", maxsplit=1)[0]
        self.assertLessEqual(
            max(map(len, status_section.splitlines())),
            120,
        )
        self.assertIn("Rows S/T", status_section)
        self.assertIn("Schema Match", status_section)
        self.assertIn("Load", status_section)
        self.assertIn("1/1", status_section)
        self.assertIn("| src.accounts", report)
        self.assertIn("| dst.accounts", report)
        self.assertIn("TABLE EXECUTION DETAILS", report)
        self.assertIn("Success", report)
        self.assertIn("Started", report)
        self.assertIn("Finished", report)
        self.assertIn("Starting multi-table full load", "\n".join(captured.output))
        self.assertIn("Discovered 2 source tables", "\n".join(captured.output))
        self.assertIn("Table load finished | status=Success", "\n".join(captured.output))
        self.assertIn("Multi-table full load completed", "\n".join(captured.output))
        self.assertFalse(source.connected)
        self.assertFalse(target.connected)

    def test_table_failure_does_not_stop_later_tables(self) -> None:
        source = FakeConnector(
            tables=["broken", "good"],
            rows={"broken": [(1, "old")], "good": [(2, "new")]},
        )
        target = FakeConnector()
        target.target_rows = {
            "broken": [(9, "preserved")],
            "good": [],
        }

        summary = self._executor(source, target).execute("src", "dst")

        self.assertEqual(summary.failed, 1)
        self.assertEqual(summary.succeeded, 1)
        self.assertIn("simulated source read failure", summary.tables[0].error_details or "")
        self.assertEqual(target.target_rows["broken"], [(9, "preserved")])
        self.assertEqual(target.target_rows["good"], [(2, "new")])
        report = summary.render_report()
        self.assertIn("TABLE EXECUTION STATUS", report)
        self.assertIn("| src.broken", report)
        self.assertIn("RuntimeError: simulated source read failure", report)
        self.assertIn("simulated source read failure", report)
        self.assertIn("TARGET TABLES LOADED (1 tables)", report)
        self.assertIn("good", report)
        self.assertNotIn("| 1 | dst     | broken", report)

    def test_count_mismatch_rolls_back_the_table(self) -> None:
        class MismatchedCountConnector(FakeConnector):
            def count_rows(self, schema_name: str, table_name: str) -> int:
                if self.target_rows:
                    return len(self.target_rows.get(table_name, [])) + 1
                return len(self.rows.get(table_name, []))

        source = FakeConnector(
            tables=["accounts"],
            rows={"accounts": [(1, "one")]},
        )
        target = MismatchedCountConnector()
        target.target_rows = {"accounts": [(9, "preserved")]}

        summary = self._executor(source, target).execute("src", "dst")

        self.assertEqual(summary.failed, 1)
        self.assertIn(
            "Record-count validation failed",
            summary.tables[0].error_details or "",
        )
        self.assertEqual(target.target_rows["accounts"], [(9, "preserved")])

    def test_only_selected_source_tables_are_full_loaded(self) -> None:
        source = FakeConnector(
            tables=["accounts", "events", "customers"],
            rows={
                "accounts": [(1, "one")],
                "events": [(2, "two")],
                "customers": [(3, "three")],
            },
        )
        target = FakeConnector()

        summary = self._executor(source, target).execute(
            source_schema="src",
            target_schema="dst",
            table_names=["customers", "accounts"],
        )

        self.assertEqual(
            summary.discovered_source_tables,
            ["accounts", "events", "customers"],
        )
        self.assertEqual(
            [result.table_name for result in summary.tables],
            ["accounts", "customers"],
        )
        self.assertEqual(
            set(target.target_rows),
            {"accounts", "customers"},
        )
        report = summary.render_report()
        self.assertIn("SOURCE TABLE DISCOVERY (3 tables)", report)
        self.assertIn("events", report)
        self.assertIn("TARGET TABLES LOADED (2 tables)", report)
        target_table_section = report.split(
            "TARGET TABLES LOADED", maxsplit=1
        )[1].split("EXECUTION SUMMARY", maxsplit=1)[0]
        self.assertNotIn("events", target_table_section)

        selective_report = render_selective_report(summary)
        self.assertNotIn("CONNECTIONS", selective_report)
        self.assertNotIn("SOURCE TABLE DISCOVERY", selective_report)
        self.assertNotIn("TABLES SELECTED FOR LOAD", selective_report)
        self.assertNotIn("SELECTED SOURCE-TO-TARGET COLUMN MAPPING", selective_report)
        self.assertIn("TARGET TABLES LOADED (2)", selective_report)
        self.assertIn("| 1 | dst           | accounts", selective_report)
        self.assertIn("TABLE EXECUTION STATUS", selective_report)
        self.assertRegex(selective_report, r"\| accounts\s+\| Success")
        self.assertRegex(selective_report, r"\| customers\s+\| Success")
        self.assertIn("EXECUTION SUMMARY", selective_report)
        self.assertGreater(
            selective_report.index("EXECUTION SUMMARY"),
            selective_report.index("TARGET TABLES LOADED"),
        )
        self.assertTrue(selective_report.splitlines()[-1].startswith("+-"))

    def test_missing_nonnullable_source_column_is_added_and_loaded(self) -> None:
        source = FakeConnector(
            tables=["orders"],
            rows={"orders": [(1, "first", "10 Main St")]},
        )
        source.column_metadata.append(
            {
                "column_name": "customer_address",
                "data_type": "text",
                "ordinal_position": 3,
                "is_nullable": "NO",
            }
        )
        target = FakeConnector()
        target.target_rows["orders"] = [(99, "stale")]

        summary = self._executor(source, target).execute("src", "dst")

        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.failed, 0)
        self.assertEqual(target.added_columns, ["customer_address"])
        self.assertEqual(
            [column["column_name"] for column in target.column_metadata],
            ["id", "value", "customer_address"],
        )
        self.assertTrue(target.column_metadata[-1]["is_nullable"])
        self.assertEqual(
            target.target_rows["orders"],
            [(1, "first", "10 Main St")],
        )
        self.assertIn(
            "added source columns to target: customer_address",
            " ".join(summary.tables[0].compatible_schema_differences),
        )

    def test_additive_schema_change_rolls_back_on_other_schema_mismatch(
        self,
    ) -> None:
        source = FakeConnector(
            tables=["orders"],
            rows={"orders": [(1, "first", "address")]},
        )
        source.column_metadata.append(
            {
                "column_name": "customer_address",
                "data_type": "text",
                "ordinal_position": 3,
                "is_nullable": "YES",
            }
        )
        target = FakeConnector()
        target.column_metadata.append(
            {
                "column_name": "legacy_note",
                "data_type": "text",
                "ordinal_position": 3,
                "is_nullable": "NO",
            }
        )
        target.target_rows["orders"] = [(99, "preserved", "legacy")]

        summary = self._executor(source, target).execute("src", "dst")

        self.assertEqual(summary.failed, 1)
        self.assertEqual(
            summary.tables[0].schema_validation_status,
            "Mismatch",
        )
        self.assertEqual(target.added_columns, ["customer_address"])
        self.assertEqual(
            [column["column_name"] for column in target.column_metadata],
            ["id", "value", "legacy_note"],
        )
        self.assertEqual(
            target.target_rows["orders"],
            [(99, "preserved", "legacy")],
        )

    def test_safe_target_widening_loads_and_is_reported(self) -> None:
        source = FakeConnector(
            tables=["orders"],
            rows={"orders": [(1, "first", 12.50)]},
        )
        source.column_metadata = [
            {
                "column_name": "order_id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
                "column_default": "nextval('orders_id_seq')",
            },
            {
                "column_name": "customer_name",
                "data_type": "character varying",
                "character_maximum_length": 100,
                "ordinal_position": 2,
                "is_nullable": "YES",
            },
            {
                "column_name": "amount",
                "data_type": "numeric",
                "numeric_precision": 10,
                "numeric_scale": 2,
                "ordinal_position": 3,
                "is_nullable": "YES",
            },
        ]
        target = FakeConnector()
        target.target_rows = {"orders": []}
        target.column_metadata = [
            {
                "column_name": "amount",
                "data_type": "numeric",
                "ordinal_position": 1,
                "is_nullable": True,
            },
            {
                "column_name": "order_id",
                "data_type": "integer",
                "ordinal_position": 2,
                "is_nullable": False,
            },
            {
                "column_name": "customer_name",
                "data_type": "text",
                "ordinal_position": 3,
                "is_nullable": True,
            },
        ]

        summary = self._executor(source, target).execute("src", "dst")
        result = summary.tables[0]

        self.assertEqual(result.status, "Success")
        self.assertEqual(
            result.schema_validation_status,
            "Mismatch",
        )
        self.assertEqual(
            result.load_compatibility_status,
            "Compatible",
        )
        self.assertTrue(result.compatible_schema_differences)
        self.assertIn("orders", target.target_rows)
        self.assertIn("Schema Match", summary.render_report())
        self.assertIn("| Load", summary.render_report())
        self.assertIn("| Mismatch", summary.render_report())
        self.assertIn("| Compatible", summary.render_report())

    def test_default_differences_do_not_mark_structural_schema_mismatch(
        self,
    ) -> None:
        source = FakeConnector(
            tables=["account"],
            rows={"account": [(1, 0.0)]},
        )
        source.column_metadata = [
            {
                "column_name": "account_id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
                "column_default": "nextval('account_id_seq')",
            },
            {
                "column_name": "balance",
                "data_type": "numeric",
                "ordinal_position": 2,
                "is_nullable": "NO",
                "column_default": "0.00",
            },
        ]
        target = FakeConnector()
        target.target_rows["account"] = []
        target.column_metadata = [
            {
                "column_name": "account_id",
                "data_type": "integer",
                "ordinal_position": 1,
                "is_nullable": "NO",
                "column_default": None,
            },
            {
                "column_name": "balance",
                "data_type": "numeric",
                "ordinal_position": 2,
                "is_nullable": "NO",
                "column_default": None,
            },
        ]

        summary = self._executor(source, target).execute("src", "dst")
        result = summary.tables[0]

        self.assertEqual(result.status, "Success")
        self.assertEqual(result.schema_validation_status, "Match")
        self.assertEqual(result.load_compatibility_status, "Compatible")
        self.assertEqual(result.schema_differences, [])
        self.assertEqual(len(result.compatible_schema_differences), 2)
        report = summary.render_report()
        self.assertIn("Schema Match", report)
        self.assertIn("| Load", report)
        self.assertIn("| Match", report)
        self.assertIn("| Compatible", report)
        self.assertIn("defaults differ", report)

    def test_created_target_is_rolled_back_when_refreshed_schema_mismatches(
        self,
    ) -> None:
        class MismatchedCreatedTarget(FakeConnector):
            def create_table(
                self,
                schema_name: str,
                table_name: str,
                columns: list[dict[str, Any]],
            ) -> None:
                super().create_table(schema_name, table_name, columns)
                self.column_metadata = [
                    dict(column) for column in self.column_metadata
                ]
                self.column_metadata[0]["data_type"] = "text"

        source = MismatchedCreatedTarget(
            tables=["orders"],
            rows={"orders": [(1, "first")]},
        )
        target = MismatchedCreatedTarget()

        summary = self._executor(source, target).execute("src", "dst")

        self.assertEqual(summary.succeeded, 0)
        self.assertEqual(summary.failed, 1)
        self.assertEqual(
            summary.tables[0].schema_validation_status,
            "Mismatch",
        )
        self.assertIn(
            "Schema metadata mismatch",
            summary.tables[0].error_details or "",
        )
        self.assertNotIn("orders", target.target_rows)
        self.assertGreaterEqual(target.rollback_count, 1)

    def test_source_dropped_column_is_omitted_without_dropping_target_column(
        self,
    ) -> None:
        source = FakeConnector(
            tables=["employee"],
            rows={"employee": [(7, "Anika")]},
        )
        original_source_columns = list(source.column_metadata)
        target = FakeConnector()
        target.column_metadata.append(
            {
                "column_name": "employee_role",
                "data_type": "text",
                "ordinal_position": 3,
                "is_nullable": "YES",
            }
        )
        target.target_rows["employee"] = [(6, "Old employee", "Analyst")]

        summary = self._executor(source, target).execute("public", "warehouse")

        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(
            summary.tables[0].schema_validation_status,
            "Mismatch",
        )
        self.assertEqual(
            summary.tables[0].load_compatibility_status,
            "Compatible",
        )
        self.assertEqual(target.dropped_columns, [])
        self.assertEqual(
            [column["column_name"] for column in target.column_metadata],
            ["id", "value", "employee_role"],
        )
        self.assertEqual(
            target.target_rows["employee"],
            [(7, "Anika", None)],
        )
        self.assertEqual(source.column_metadata, original_source_columns)
        self.assertEqual(source.dropped_columns, [])

    def test_nullable_target_only_columns_are_reported_and_preserved(self) -> None:
        source = FakeConnector(
            tables=["employee"],
            rows={"employee": [(8, "Sam")]},
        )
        source_columns_before = list(source.column_metadata)
        source_rows_before = dict(source.rows)
        target = FakeConnector()
        target.column_metadata.extend(
            [
                {
                    "column_name": "employee_role",
                    "data_type": "text",
                    "ordinal_position": 3,
                    "is_nullable": "YES",
                },
                {
                    "column_name": "legacy_note",
                    "data_type": "text",
                    "ordinal_position": 4,
                    "is_nullable": "YES",
                },
            ]
        )
        target.target_rows["employee"] = [(1, "Old", "Analyst", "Legacy")]

        summary = self._executor(source, target).execute("public", "warehouse")

        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(
            summary.tables[0].schema_validation_status,
            "Mismatch",
        )
        self.assertEqual(
            summary.tables[0].load_compatibility_status,
            "Compatible",
        )
        self.assertEqual(target.dropped_columns, [])
        self.assertEqual(
            [column["column_name"] for column in target.column_metadata],
            [
                "id",
                "value",
                "employee_role",
                "legacy_note",
            ],
        )
        self.assertEqual(
            target.target_rows["employee"],
            [(8, "Sam", None, None)],
        )
        self.assertEqual(source.column_metadata, source_columns_before)
        self.assertEqual(source.rows, source_rows_before)
        self.assertEqual(source.dropped_columns, [])

    def test_unsafe_target_schema_mismatch_sets_status_and_preserves_rows(
        self,
    ) -> None:
        source = FakeConnector(
            tables=["employee"],
            rows={"employee": [(8, "Sam")]},
        )
        target = FakeConnector()
        target.column_metadata[0]["data_type"] = "text"
        target.target_rows["employee"] = [(1, "Existing")]
        summary = self._executor(source, target).execute("public", "warehouse")

        self.assertEqual(summary.failed, 1)
        self.assertEqual(
            summary.tables[0].schema_validation_status,
            "Mismatch",
        )
        self.assertEqual(
            summary.tables[0].load_compatibility_status,
            "Blocked",
        )
        self.assertEqual(target.rollback_count, 1)
        self.assertEqual(
            target.target_rows["employee"],
            [(1, "Existing")],
        )
        self.assertEqual(
            [column["column_name"] for column in target.column_metadata],
            ["id", "value"],
        )
        self.assertIn(
            "target was not loaded",
            summary.tables[0].error_details or "",
        )
        self.assertEqual(source.dropped_columns, [])

    def test_empty_source_table_truncates_existing_target_table(self) -> None:
        source = FakeConnector(
            tables=["employee"],
            rows={"employee": []},
        )
        target = FakeConnector()
        target.target_rows["employee"] = [(1, "Stale employee")]

        summary = self._executor(source, target).execute("public", "warehouse")

        self.assertEqual(summary.succeeded, 1)
        self.assertEqual(summary.tables[0].source_record_count, 0)
        self.assertEqual(summary.tables[0].target_record_count, 0)
        self.assertEqual(target.target_rows["employee"], [])
        self.assertEqual(target.added_columns, [])
        self.assertEqual(target.dropped_columns, [])

    def test_interactive_report_shows_source_discovery(self) -> None:
        discovery_report = render_discovery_report(
            "public",
            ["Order", "account", "customer"],
        )
        self.assertIn("SOURCE TABLE DISCOVERY (3 tables)", discovery_report)
        self.assertIn("| 1 | public        | Order", discovery_report)
        self.assertIn("| 3 | public        | customer", discovery_report)

        selected_report = render_selected_tables(["Order", "customer"])
        self.assertIn("TABLES SELECTED FOR LOAD (2)", selected_report)
        self.assertIn("| 1 | Order", selected_report)
        self.assertIn("| 2 | customer", selected_report)

    def test_rejects_unknown_selected_tables(self) -> None:
        source = FakeConnector(tables=["accounts"])
        target = FakeConnector()

        with self.assertRaisesRegex(ValueError, "not found"):
            self._executor(source, target).execute(
                source_schema="src",
                target_schema="dst",
                table_names=["missing"],
            )

    def test_interactive_selection_is_validated_against_discovery(self) -> None:
        self.assertEqual(
            parse_table_selection(
                "customers, accounts, customers",
                ["accounts", "customers", "events"],
            ),
            ["customers", "accounts"],
        )
        with self.assertRaisesRegex(ValueError, "not found"):
            parse_table_selection("unknown", ["accounts", "customers"])
        self.assertEqual(
            parse_table_selection("1, 3", ["accounts", "events", "customers"]),
            ["accounts", "customers"],
        )


if __name__ == "__main__":
    unittest.main()
