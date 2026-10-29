from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.runtime.unified_full_load_cli import (
    _identifier_code,
    _normalize_columns,
    _onboard_table,
    _print_connection,
    _prompt_for_missing_arguments,
    _prompt_for_load_confirmation,
    _prompt_for_missing_scope,
    _resolve_scope_from_bindings,
    _select_tables,
)


class UnifiedFullLoadCliTests(unittest.TestCase):
    def test_select_tables_accepts_all_case_insensitively(self) -> None:
        discovered = ["account", "employee"]

        self.assertEqual(_select_tables(["all"], discovered), discovered)

    def test_select_tables_accepts_discovery_indexes_and_names(self) -> None:
        self.assertEqual(
            _select_tables(["2", "account"], ["account", "employee"]),
            ["employee", "account"],
        )

    def test_select_tables_rejects_all_combined_with_names(self) -> None:
        with self.assertRaisesRegex(ValueError, "ALL cannot be combined"):
            _select_tables(["ALL", "employee"], ["employee"])

    def test_interactive_table_menu_selects_all_tables(self) -> None:
        with patch("builtins.input", return_value="1"):
            self.assertEqual(
                _select_tables(None, ["account", "employee"]),
                ["account", "employee"],
            )

    def test_interactive_table_menu_selects_named_tables(self) -> None:
        with patch("builtins.input", side_effect=["2", "2"]):
            self.assertEqual(
                _select_tables(None, ["account", "employee"]),
                ["employee"],
            )

    def test_missing_connection_and_schema_arguments_are_prompted(self) -> None:
        args = SimpleNamespace(
            source_connection_id=None,
            target_connection_id=None,
            source_schema=None,
            target_schema=None,
            tenant_id=None,
            project_id=None,
            environment_id=None,
        )
        responses = ["1", "11", "public", "warehouse"]

        with patch("builtins.input", side_effect=responses) as prompt:
            _prompt_for_missing_arguments(args)

        self.assertEqual(args.source_connection_id, 1)
        self.assertEqual(args.target_connection_id, 11)
        self.assertEqual(args.source_schema, "public")
        self.assertEqual(args.target_schema, "warehouse")
        self.assertEqual(prompt.call_count, 4)

    def test_scope_is_inferred_from_unique_active_bindings(self) -> None:
        args = SimpleNamespace(
            source_connection_id=1,
            target_connection_id=11,
            tenant_id=None,
            project_id=None,
            environment_id=None,
        )
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(1, 1, 1)]

        with patch(
            "app.runtime.unified_full_load_cli.get_metastore_connection",
            return_value=connection,
        ):
            inferred = _resolve_scope_from_bindings(args)

        self.assertTrue(inferred)
        self.assertEqual(
            (args.tenant_id, args.project_id, args.environment_id),
            (1, 1, 1),
        )
        cursor.execute.assert_called_once()

    def test_scope_prompts_only_when_not_inferred(self) -> None:
        args = SimpleNamespace(
            tenant_id=None,
            project_id=None,
            environment_id=None,
        )

        with patch("builtins.input", side_effect=["1", "2", "3"]) as prompt:
            _prompt_for_missing_scope(args)

        self.assertEqual(
            (args.tenant_id, args.project_id, args.environment_id),
            (1, 2, 3),
        )
        self.assertEqual(prompt.call_count, 3)

    def test_load_confirmation_accepts_yes(self) -> None:
        with patch("builtins.input", return_value="yes"):
            self.assertTrue(_prompt_for_load_confirmation())

    def test_load_confirmation_defaults_to_no(self) -> None:
        with patch("builtins.input", return_value=""):
            self.assertFalse(_prompt_for_load_confirmation())

    def test_non_interactive_missing_argument_is_reported(self) -> None:
        args = SimpleNamespace(
            source_connection_id=None,
            target_connection_id=11,
            source_schema="public",
            target_schema="warehouse",
            tenant_id=2,
            project_id=3,
            environment_id=4,
        )

        with (
            patch("builtins.input", side_effect=EOFError),
            self.assertRaisesRegex(
                ValueError,
                "--source-connection-id is required when running non-interactively",
            ),
        ):
            _prompt_for_missing_arguments(args)

    def test_normalize_columns_preserves_supported_catalog_attributes(self) -> None:
        columns = _normalize_columns(
            [
                {
                    "column_name": "amount",
                    "data_type": "numeric",
                    "ordinal_position": 1,
                    "is_nullable": "NO",
                    "numeric_precision": 12,
                    "numeric_scale": 2,
                    "column_default": "0",
                }
            ]
        )

        self.assertEqual(
            columns,
            [
                {
                    "ordinal_position": 1,
                    "field_name": "amount",
                    "field_name_normalized": "amount",
                    "source_datatype_text": "numeric",
                    "is_nullable": False,
                    "default_expression": "0",
                    "length_value": None,
                    "precision_value": 12,
                    "scale_value": 2,
                    "datetime_precision": None,
                    "is_identity": False,
                    "is_generated": False,
                }
            ],
        )

    def test_identifier_codes_are_stable_and_safe(self) -> None:
        code = _identifier_code("FULL", "1", "public", "Customer Table")

        self.assertEqual(
            code, _identifier_code("FULL", "1", "public", "Customer Table")
        )
        self.assertTrue(code.startswith("FULL_"))
        self.assertTrue(code.replace("_", "").isalnum())

    def test_connection_report_does_not_expose_endpoint_credentials(self) -> None:
        metadata = SimpleNamespace(
            connection_id=4,
            connection_name="example",
            connector_code="POSTGRESQL_CONNECTOR",
            host_name="db.example",
            port_no=5432,
            database_name="warehouse",
            endpoint_url="postgresql://user:secret@db.example:5432/warehouse?token=hidden",
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_connection("Source", metadata)

        report = output.getvalue()
        self.assertIn("endpoint=postgresql://db.example:5432/warehouse", report)
        self.assertNotIn("secret", report)
        self.assertNotIn("token", report)

    def test_onboard_table_commits_complete_mapping_metadata(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        source_fields = [
            {
                "field_id": 101,
                "field_name": "employee_id",
                "native_datatype_id": 1,
                "ordinal_no": 1,
            }
        ]
        target_fields = [
            {
                "field_id": 201,
                "field_name": "employee_id",
                "native_datatype_id": 1,
                "ordinal_no": 1,
            }
        ]
        mapping_result = {
            "mapping_id": 301,
            "mapping_version_id": 401,
            "mapping_status": "DRAFT",
            "pipeline_id": 501,
            "pipeline_version_id": 601,
            "pipeline_status": "DRAFT",
        }

        with (
            patch(
                "app.runtime.unified_full_load_cli.get_metastore_connection",
                return_value=connection,
            ),
            patch(
                "app.runtime.unified_full_load_cli._resolve_mapping_set",
                return_value=7,
            ),
            patch(
                "app.runtime.unified_full_load_cli._create_or_find_binding",
                side_effect=[(11, 12), (21, 22)],
            ),
            patch(
                "app.runtime.unified_full_load_cli._capture_schema_version",
                side_effect=[(31, source_fields), (41, target_fields)],
            ),
            patch(
                "app.runtime.unified_full_load_cli._create_mapping_and_pipeline",
                return_value=mapping_result,
            ) as create_mapping,
        ):
            result = _onboard_table(
                source_metadata=SimpleNamespace(
                    connection_id=1,
                    database_name="source",
                    connector_version_id=2,
                    connector_id=3,
                ),
                target_metadata=SimpleNamespace(
                    connection_id=11,
                    database_name="target",
                    connector_version_id=4,
                    connector_id=5,
                ),
                source_columns=[
                    {
                        "column_name": "employee_id",
                        "ordinal_position": 1,
                    }
                ],
                target_columns=[{"column_name": "employee_id"}],
                source_schema="public",
                target_schema="warehouse",
                table_name="employee",
                tenant_id=1,
                project_id=2,
                environment_id=3,
                batch_size=100,
                datatype_mapping_set_id=None,
            )

        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()
        create_mapping.assert_called_once()
        self.assertEqual(
            create_mapping.call_args.kwargs["source_fields"],
            source_fields,
        )
        self.assertEqual(
            create_mapping.call_args.kwargs["target_fields"],
            target_fields,
        )
        self.assertEqual(result["mapping_status"], "DRAFT")
        self.assertEqual(result["pipeline_status"], "DRAFT")
        self.assertEqual(result["source_binding_id"], 12)
        self.assertEqual(result["target_binding_id"], 22)

    def test_onboard_table_rolls_back_when_mapping_setup_fails(self) -> None:
        connection = MagicMock()
        connection.__enter__.return_value = connection
        connection.cursor.return_value.__enter__.return_value = MagicMock()

        with (
            patch(
                "app.runtime.unified_full_load_cli.get_metastore_connection",
                return_value=connection,
            ),
            patch(
                "app.runtime.unified_full_load_cli._resolve_mapping_set",
                return_value=7,
            ),
            patch(
                "app.runtime.unified_full_load_cli._create_or_find_binding",
                side_effect=[(11, 12), (21, 22)],
            ),
            patch(
                "app.runtime.unified_full_load_cli._capture_schema_version",
                side_effect=[
                    (
                        31,
                        [
                            {
                                "field_id": 101,
                                "field_name": "employee_id",
                                "native_datatype_id": 1,
                                "ordinal_no": 1,
                            }
                        ],
                    ),
                    (
                        41,
                        [
                            {
                                "field_id": 201,
                                "field_name": "employee_id",
                                "native_datatype_id": 1,
                                "ordinal_no": 1,
                            }
                        ],
                    ),
                ],
            ),
            patch(
                "app.runtime.unified_full_load_cli._create_mapping_and_pipeline",
                side_effect=ValueError("mapping insert failed"),
            ),
            patch("app.runtime.unified_full_load_cli.logger.exception"),
        ):
            with self.assertRaisesRegex(ValueError, "mapping insert failed"):
                _onboard_table(
                    source_metadata=SimpleNamespace(
                        connection_id=1,
                        database_name="source",
                        connector_version_id=2,
                        connector_id=3,
                    ),
                    target_metadata=SimpleNamespace(
                        connection_id=11,
                        database_name="target",
                        connector_version_id=4,
                        connector_id=5,
                    ),
                    source_columns=[
                        {
                            "column_name": "employee_id",
                            "ordinal_position": 1,
                        }
                    ],
                    target_columns=[{"column_name": "employee_id"}],
                    source_schema="public",
                    target_schema="warehouse",
                    table_name="employee",
                    tenant_id=1,
                    project_id=2,
                    environment_id=3,
                    batch_size=100,
                    datatype_mapping_set_id=7,
                )

        connection.rollback.assert_called_once_with()
        connection.commit.assert_not_called()

    def test_onboard_table_rejects_missing_target_column_before_transaction(
        self,
    ) -> None:
        with (
            patch(
                "app.runtime.unified_full_load_cli.get_metastore_connection"
            ) as get_connection,
        ):
            with self.assertRaisesRegex(ValueError, "missing source columns"):
                _onboard_table(
                    source_metadata=SimpleNamespace(),
                    target_metadata=SimpleNamespace(),
                    source_columns=[
                        {
                            "column_name": "employee_id",
                            "ordinal_position": 1,
                        }
                    ],
                    target_columns=[],
                    source_schema="public",
                    target_schema="warehouse",
                    table_name="employee",
                    tenant_id=1,
                    project_id=2,
                    environment_id=3,
                    batch_size=100,
                    datatype_mapping_set_id=None,
                )

        get_connection.assert_not_called()
