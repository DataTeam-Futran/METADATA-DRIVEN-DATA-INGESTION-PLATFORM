import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.core.config import _load_environment
from app.credentials.providers.demo import DemoSecretProvider
from incremental_loading.scripts.dynamic_source_target_setup import (
    ConfigurationError,
    _validate_direct_endpoint,
    _check_endpoint_privileges,
    build_parser,
    load_config,
    parse_config,
    verify_schema,
)


EXAMPLE_CONFIG = (
    Path(__file__).parents[3]
    / "incremental_loading"
    / "scripts"
    / "setup.example.json"
)


class FakeSchemaCursor:
    def __init__(self, missing_column: str | None = None) -> None:
        self.missing_column = missing_column
        self.rows: list[tuple[str, str, str | None, str | None]] = []

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        if "information_schema.columns" not in query:
            raise AssertionError("Unexpected schema preflight query.")
        table_names = params[0]
        from incremental_loading.scripts.dynamic_source_target_setup import (
            IDENTITY_COLUMNS,
            REQUIRED_COLUMNS,
        )

        for table, columns in REQUIRED_COLUMNS.items():
            for column in columns:
                if f"{table}.{column}" == self.missing_column:
                    continue
                is_identity = "NO"
                generation = None
                if column == IDENTITY_COLUMNS[table]:
                    is_identity = "YES"
                    generation = "ALWAYS"
                self.rows.append((table, column, is_identity, generation))
        self.rows = [row for row in self.rows if row[0].split(".", 1)[1] in table_names]

    def fetchall(self) -> list[tuple[str, str, str | None, str | None]]:
        return self.rows


class FakePrivilegeCursor:
    def __init__(self) -> None:
        self.query = ""
        self.queries: list[str] = []

    def __enter__(self) -> "FakePrivilegeCursor":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, query: str, _params: tuple[object, ...]) -> None:
        self.query = query
        self.queries.append(query)

    def fetchone(self) -> tuple[str, str, bool, bool, bool, bool] | tuple[bool]:
        if "has_table_privilege" in self.query:
            return (True,)
        return ("demo_source_db", "postgres", True, True, True, True)

    def fetchall(self) -> list[tuple[str]]:
        if "pg_catalog.pg_tables" in self.query:
            if "SELECT tablename" not in self.query:
                raise AssertionError("pg_tables query must select its tablename column.")
            return [("source_table",)]
        raise AssertionError("Unexpected privilege query.")


class FakePrivilegeConnection:
    def __init__(self) -> None:
        self.cursor_instance = FakePrivilegeCursor()

    def cursor(self) -> FakePrivilegeCursor:
        return self.cursor_instance


class DynamicSetupTests(unittest.TestCase):
    def test_explicit_environment_file_is_loaded_as_authoritative(self) -> None:
        environment_file = "environments/preprod/preprod.env"
        with patch.dict(os.environ, {"MDIP_ENV_FILE": environment_file}):
            with patch("app.core.config.load_dotenv") as load_dotenv:
                _load_environment()
        load_dotenv.assert_called_once_with(
            dotenv_path=environment_file,
            override=True,
        )

    def test_default_dotenv_discovery_is_preserved(self) -> None:
        with patch.dict(os.environ, {"MDIP_ENV_FILE": ""}):
            with patch("app.core.config.load_dotenv") as load_dotenv:
                _load_environment()
        load_dotenv.assert_called_once_with()

    def test_example_config_loads_without_generated_ids(self) -> None:
        config = load_config(EXAMPLE_CONFIG)
        self.assertEqual(config.source.role, "SOURCE")
        self.assertEqual(config.target.role, "TARGET")
        self.assertEqual(config.source.secret_ref, "env:MDIP_DB_SECRET_SOURCE")
        self.assertEqual(config.target.secret_ref, "env:MDIP_DB_SECRET_TARGET")

    def test_config_rejects_plaintext_password_keys(self) -> None:
        raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        raw["source"]["source_password"] = "must-not-be-stored"
        with self.assertRaisesRegex(ConfigurationError, "not allowed"):
            parse_config(raw)

    def test_config_rejects_unrestricted_environment_variable_names(self) -> None:
        raw = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        raw["source"]["secret_env_var"] = "HOME"
        with self.assertRaisesRegex(ConfigurationError, "must start with"):
            parse_config(raw)

    def test_secret_provider_resolves_prefixed_env_reference(self) -> None:
        provider = DemoSecretProvider()
        with patch.dict(os.environ, {"MDIP_DB_SECRET_SOURCE": "test-secret"}):
            self.assertEqual(
                provider.get_secret("env:MDIP_DB_SECRET_SOURCE"),
                "test-secret",
            )

    def test_secret_provider_rejects_unrestricted_env_reference(self) -> None:
        provider = DemoSecretProvider()
        with self.assertRaisesRegex(ValueError, "Unsupported DEMO secret reference"):
            provider.get_secret("env:PATH")

    def test_endpoint_validation_reports_underlying_connection_error(self) -> None:
        config = load_config(EXAMPLE_CONFIG)
        with (
            patch.dict(os.environ, {"MDIP_DB_SECRET_SOURCE": "test-secret"}),
            patch(
                "incremental_loading.scripts.dynamic_source_target_setup.psycopg.connect",
                side_effect=RuntimeError("column test_column does not exist"),
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                r"RuntimeError: column test_column does not exist",
            ):
                _validate_direct_endpoint(config.source)

    def test_existing_demo_secret_reference_remains_supported(self) -> None:
        provider = DemoSecretProvider()
        with patch.dict(os.environ, {"MDIP_DEMO_POSTGRES_PASSWORD": "legacy-secret"}):
            self.assertEqual(provider.get_secret("POSTGRES_DEV_SECRET"), "legacy-secret")

    def test_live_schema_preflight_requires_expected_identity_columns(self) -> None:
        verify_schema(FakeSchemaCursor())

    def test_live_schema_preflight_rejects_missing_required_column(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "sec.tenant missing tenant_code"):
            verify_schema(FakeSchemaCursor("sec.tenant.tenant_code"))

    def test_endpoint_privilege_check_queries_postgres_table_name_column(self) -> None:
        config = load_config(EXAMPLE_CONFIG)
        connection = FakePrivilegeConnection()
        _check_endpoint_privileges(connection, config.source)
        privilege_query = next(
            query
            for query in connection.cursor_instance.queries
            if "has_table_privilege" in query
        )
        self.assertIn("quote_ident(%s)", privilege_query)
        self.assertNotIn("%I", privilege_query)

    def test_cli_exposes_setup_inspection_and_validation_commands(self) -> None:
        parser = build_parser()
        for command in ("setup", "inspect", "validate", "inspect-schema"):
            with self.subTest(command=command):
                args = parser.parse_args([command, *(["--config", str(EXAMPLE_CONFIG)] if command != "inspect-schema" else [])])
                self.assertEqual(args.command, command)


if __name__ == "__main__":
    unittest.main()
