"""Create, inspect, and validate PostgreSQL connection metadata dynamically.

Run from the innermost project directory:

    python -m incremental_loading.scripts.dynamic_source_target_setup --help

The metadata database is read from the application's MDIP_METASTORE_*
settings. Source and target passwords are never accepted as CLI arguments or
stored in metadata. They are resolved from environment variables through the
existing DEMO credential provider using secret references such as
``env:MDIP_DB_SECRET_SOURCE``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psycopg

from app.db.metastore import get_metastore_connection
from app.runtime.connection_resolver import RuntimeConnectionResolver


LOGGER = logging.getLogger("dynamic_source_target_setup")
POSTGRESQL_CONNECTOR_ID = 3
POSTGRESQL_CONNECTOR_CODE = "POSTGRESQL_CONNECTOR"
PASSWORD_AUTH_METHOD_CODE = "PASSWORD"
SECRET_ENV_PREFIX = "MDIP_DB_SECRET_"
ENV_SECRET_PATTERN = re.compile(r"^MDIP_DB_SECRET_[A-Z0-9_]+$")
SYSTEM_DESCRIPTION = "PostgreSQL demo_source system"
REQUIRED_COLUMNS: dict[str, set[str]] = {
    "sec.tenant": {"tenant_id", "tenant_code", "tenant_name", "status_code"},
    "sec.project": {
        "project_id", "tenant_id", "project_code", "project_name", "status_code"
    },
    "sec.environment": {
        "environment_id", "tenant_id", "environment_code", "environment_name",
        "environment_rank", "status_code",
    },
    "conn.source_system": {
        "system_id", "tenant_id", "project_id", "system_code", "system_name",
        "description", "status_code",
    },
    "conn.credential_ref": {
        "credential_id", "tenant_id", "auth_method_id", "credential_name",
        "secret_provider_code", "secret_ref", "status_code",
    },
    "conn.connection_profile": {
        "connection_id", "tenant_id", "system_id", "environment_id",
        "connector_version_id", "credential_id", "connection_role_code",
        "connection_name", "host_name", "port_no", "database_name",
        "endpoint_url", "connect_timeout_seconds", "command_timeout_seconds",
        "status_code",
    },
    "conn.connection_parameter": {
        "connection_parameter_id", "connection_id", "parameter_name",
        "parameter_value", "value_type_code", "is_secret_ref",
        "environment_override",
    },
}
IDENTITY_COLUMNS = {
    "sec.tenant": "tenant_id",
    "sec.project": "project_id",
    "sec.environment": "environment_id",
    "conn.source_system": "system_id",
    "conn.credential_ref": "credential_id",
    "conn.connection_profile": "connection_id",
    "conn.connection_parameter": "connection_parameter_id",
}


class ConfigurationError(ValueError):
    """Raised when CLI/configuration inputs are incomplete or unsafe."""


@dataclass(frozen=True)
class Endpoint:
    role: str
    name: str
    host: str
    port: int
    database: str
    schema: str
    username: str
    credential_name: str
    secret_env_var: str
    sslmode: str
    connect_timeout_seconds: int
    command_timeout_seconds: int

    @property
    def secret_ref(self) -> str:
        return f"env:{self.secret_env_var}"

    @property
    def endpoint_url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host and not self.host.startswith("[") else self.host
        return f"postgresql://{host}:{self.port}/{quote(self.database, safe='')}"


@dataclass(frozen=True)
class SetupConfig:
    tenant_code: str
    tenant_name: str
    tenant_description: str
    project_code: str
    project_name: str
    project_description: str
    environment_code: str
    environment_name: str
    environment_rank: int
    system_code: str
    system_name: str
    source: Endpoint
    target: Endpoint


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"{label} must be a non-empty string.")
    return value.strip()


def _reject_plaintext_secrets(value: Any, path: str = "config") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = key.lower()
            if (
                "password" in normalized_key
                or "passwd" in normalized_key
                or "credential_value" in normalized_key
                or (
                    "secret" in normalized_key
                    and not normalized_key.endswith("_env_var")
                )
            ):
                raise ConfigurationError(
                    f"{path}.{key} is not allowed; configure a secret environment "
                    "variable name instead."
                )
            _reject_plaintext_secrets(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_plaintext_secrets(item, f"{path}[{index}]")


def _make_endpoint(data: Any, role: str) -> Endpoint:
    if not isinstance(data, dict):
        raise ConfigurationError(f"{role} must be a JSON object.")
    required = (
        "name", "host", "port", "database", "schema", "username",
        "credential_name", "secret_env_var",
    )
    missing = [key for key in required if key not in data]
    if missing:
        raise ConfigurationError(
            f"{role} is missing required field(s): {', '.join(missing)}."
        )
    host = _required_text(data["host"], f"{role}.host")
    if any(char.isspace() for char in host):
        raise ConfigurationError(f"{role}.host must not contain whitespace.")
    try:
        port = int(data["port"])
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{role}.port must be an integer.") from error
    if not 1 <= port <= 65535:
        raise ConfigurationError(f"{role}.port must be between 1 and 65535.")
    try:
        connect_timeout = int(data.get("connect_timeout_seconds", 10))
        command_timeout = int(data.get("command_timeout_seconds", 600))
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{role} timeouts must be integers.") from error
    if connect_timeout <= 0 or command_timeout <= 0:
        raise ConfigurationError(f"{role} timeouts must be greater than zero.")

    secret_env_var = _required_text(
        data["secret_env_var"], f"{role}.secret_env_var"
    )
    if not ENV_SECRET_PATTERN.fullmatch(secret_env_var):
        raise ConfigurationError(
            f"{role}.secret_env_var must start with {SECRET_ENV_PREFIX} and "
            "contain only uppercase letters, digits, and underscores."
        )

    return Endpoint(
        role=role.upper(),
        name=_required_text(data["name"], f"{role}.name"),
        host=host,
        port=port,
        database=_required_text(data["database"], f"{role}.database"),
        schema=_required_text(data["schema"], f"{role}.schema"),
        username=_required_text(data["username"], f"{role}.username"),
        credential_name=_required_text(
            data["credential_name"], f"{role}.credential_name"
        ),
        secret_env_var=secret_env_var,
        sslmode=_required_text(data.get("sslmode", "prefer"), f"{role}.sslmode"),
        connect_timeout_seconds=connect_timeout,
        command_timeout_seconds=command_timeout,
    )


def parse_config(raw: Any) -> SetupConfig:
    if not isinstance(raw, dict):
        raise ConfigurationError("The configuration root must be a JSON object.")
    _reject_plaintext_secrets(raw)
    for section in ("tenant", "project", "environment", "system"):
        if not isinstance(raw.get(section), dict):
            raise ConfigurationError(f"config.{section} must be a JSON object.")
    tenant = raw["tenant"]
    project = raw["project"]
    environment = raw["environment"]
    system = raw["system"]
    try:
        rank = int(environment["rank"])
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigurationError("environment.rank must be an integer.") from error
    if not 0 <= rank <= 32767:
        raise ConfigurationError("environment.rank must be between 0 and 32767.")
    system_code = _required_text(system.get("code"), "system.code")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", system_code):
        raise ConfigurationError("system.code may contain only letters, digits, _ and -.")

    return SetupConfig(
        tenant_code=_required_text(tenant.get("code"), "tenant.code"),
        tenant_name=_required_text(tenant.get("name"), "tenant.name"),
        tenant_description=str(tenant.get("description", "")).strip(),
        project_code=_required_text(project.get("code"), "project.code"),
        project_name=_required_text(project.get("name"), "project.name"),
        project_description=str(project.get("description", "")).strip(),
        environment_code=_required_text(environment.get("code"), "environment.code"),
        environment_name=_required_text(environment.get("name"), "environment.name"),
        environment_rank=rank,
        system_code=system_code,
        system_name=_required_text(system.get("name"), "system.name"),
        source=_make_endpoint(raw.get("source"), "source"),
        target=_make_endpoint(raw.get("target"), "target"),
    )


def load_config(path: Path) -> SetupConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigurationError(f"Cannot read configuration file {path}.") from error
    except json.JSONDecodeError as error:
        raise ConfigurationError(
            f"Configuration file is not valid JSON (line {error.lineno})."
        ) from error
    return parse_config(raw)


def interactive_config() -> SetupConfig:
    """Collect non-secret metadata interactively; secrets remain in the environment."""
    print("Enter database metadata inputs. Passwords are not prompted or stored.")
    raw: dict[str, Any] = {}
    raw["tenant"] = {
        "code": input("Tenant code: ").strip(),
        "name": input("Tenant name: ").strip(),
        "description": input("Tenant description (optional): ").strip(),
    }
    raw["project"] = {
        "code": input("Project code: ").strip(),
        "name": input("Project name: ").strip(),
        "description": input("Project description (optional): ").strip(),
    }
    raw["environment"] = {
        "code": input("Environment code: ").strip(),
        "name": input("Environment name: ").strip(),
        "rank": input("Environment rank (integer): ").strip(),
    }
    raw["system"] = {
        "code": input("PostgreSQL system code: ").strip(),
        "name": input("System name: ").strip(),
    }
    for role in ("source", "target"):
        print(f"\n{role.title()} endpoint")
        raw[role] = {
            "name": input("Connection profile name: ").strip(),
            "host": input("Host: ").strip(),
            "port": input("Port: ").strip(),
            "database": input("Database name: ").strip(),
            "schema": input("Schema: ").strip(),
            "username": input("Database username: ").strip(),
            "credential_name": input("Credential reference name: ").strip(),
            "secret_env_var": input(
                f"Secret environment variable name (must start {SECRET_ENV_PREFIX}): "
            ).strip(),
            "sslmode": input("PostgreSQL sslmode [prefer]: ").strip() or "prefer",
        }
    return parse_config(raw)


def verify_schema(cursor: Any) -> None:
    """Fail fast if the connected metadata database differs from inspected DDL."""
    cursor.execute(
        """
        SELECT table_schema || '.' || table_name, column_name, is_identity,
               identity_generation
        FROM information_schema.columns
        WHERE table_schema IN ('sec', 'conn')
          AND table_name = ANY(%s)
        """,
        ([table.rsplit(".", 1)[1] for table in REQUIRED_COLUMNS],),
    )
    found: dict[str, set[str]] = {table: set() for table in REQUIRED_COLUMNS}
    identities: dict[str, tuple[str, str | None]] = {}
    for table_name, column_name, is_identity, generation in cursor.fetchall():
        if table_name not in found:
            continue
        found[table_name].add(column_name)
        if column_name == IDENTITY_COLUMNS[table_name]:
            identities[table_name] = (is_identity, generation)
    problems = [
        f"{table} missing {', '.join(sorted(columns - found[table]))}"
        for table, columns in REQUIRED_COLUMNS.items()
        if columns - found[table]
    ]
    problems.extend(
        f"{table}.{identity} is not GENERATED ALWAYS AS IDENTITY"
        for table, identity in IDENTITY_COLUMNS.items()
        if identities.get(table) != ("YES", "ALWAYS")
    )
    if problems:
        raise RuntimeError(
            "Metadata schema does not match the inspected PostgreSQL layout: "
            + "; ".join(problems)
        )


def validate_postgresql_connector(cursor: Any) -> tuple[int, int, int]:
    cursor.execute(
        """
        SELECT connector_id, connector_code, connector_name,
               status_code, supports_source, supports_target
        FROM conn.connector
        WHERE connector_id = %s
        """,
        (POSTGRESQL_CONNECTOR_ID,),
    )
    connector = cursor.fetchone()
    if connector is None:
        raise LookupError(
            f"Required connector ID {POSTGRESQL_CONNECTOR_ID} does not exist."
        )
    connector_id, code, name, status, supports_source, supports_target = connector
    if code != POSTGRESQL_CONNECTOR_CODE:
        raise RuntimeError(
            f"Connector ID {connector_id} is {code!r}, not the required "
            f"{POSTGRESQL_CONNECTOR_CODE!r}; refusing to register profiles."
        )
    if status != "ACTIVE" or not supports_source or not supports_target:
        raise RuntimeError(
            f"Connector {code} must be ACTIVE and support SOURCE and TARGET."
        )
    cursor.execute(
        """
        SELECT connector_version_id
        FROM conn.connector_version
        WHERE connector_id = %s AND status_code = 'ACTIVE'
        ORDER BY released_at DESC NULLS LAST, semantic_version DESC
        LIMIT 1
        """,
        (connector_id,),
    )
    version = cursor.fetchone()
    if version is None:
        raise LookupError(f"No ACTIVE version exists for {code}.")
    connector_version_id = int(version[0])
    cursor.execute(
        """
        SELECT auth_method_id, required_fields
        FROM conn.connector_auth_method
        WHERE connector_id = %s
          AND auth_method_code = %s
          AND status_code = 'ACTIVE'
        ORDER BY auth_method_id
        LIMIT 1
        """,
        (connector_id, PASSWORD_AUTH_METHOD_CODE),
    )
    auth_method = cursor.fetchone()
    if auth_method is None:
        raise LookupError(
            f"No ACTIVE {PASSWORD_AUTH_METHOD_CODE} auth method exists "
            f"for connector {code}."
        )
    auth_method_id, required_fields = auth_method
    if not {"username", "credential_ref"}.issubset(set(required_fields)):
        raise RuntimeError(
            f"Auth method {PASSWORD_AUTH_METHOD_CODE} does not declare "
            "username and credential_ref as required fields."
        )
    LOGGER.info(
        "Validated connector %s (%s), active version ID %s and auth method ID %s.",
        connector_id,
        name,
        connector_version_id,
        auth_method_id,
    )
    return connector_id, connector_version_id, int(auth_method_id)


def _find_or_insert(
    cursor: Any,
    select_query: str,
    select_params: tuple[Any, ...],
    insert_query: str,
    insert_params: tuple[Any, ...],
    id_label: str,
    compare: tuple[Any, ...],
) -> tuple[int, bool]:
    cursor.execute(select_query, select_params)
    row = cursor.fetchone()
    if row is not None:
        entity_id, *existing = row
        values_match = len(existing) == len(compare) and all(
            (
                str(actual).upper() == "ACTIVE"
                if index == len(compare) - 1
                and isinstance(expected, str)
                and expected.upper() == "ACTIVE"
                else actual == expected
            )
            for index, (actual, expected) in enumerate(zip(existing, compare))
        )
        if not values_match:
            raise ValueError(
                f"An existing record conflicts with the requested {id_label}; "
                "use a new natural key or reconcile it explicitly."
            )
        return int(entity_id), False
    cursor.execute(insert_query, insert_params)
    inserted = cursor.fetchone()
    if inserted is None or inserted[0] is None:
        raise RuntimeError(f"Database did not return the generated {id_label}.")
    return int(inserted[0]), True


def _tenant(cursor: Any, config: SetupConfig) -> tuple[int, bool]:
    return _find_or_insert(
        cursor,
        "SELECT tenant_id, tenant_name, COALESCE(description, ''), status_code "
        "FROM sec.tenant WHERE tenant_code = %s",
        (config.tenant_code,),
        """
        INSERT INTO sec.tenant (tenant_code, tenant_name, description, status_code)
        VALUES (%s, %s, %s, 'ACTIVE') RETURNING tenant_id
        """,
        (config.tenant_code, config.tenant_name, config.tenant_description or None),
        "tenant_id",
        (config.tenant_name, config.tenant_description, "ACTIVE"),
    )


def _project(cursor: Any, config: SetupConfig, tenant_id: int) -> tuple[int, bool]:
    return _find_or_insert(
        cursor,
        "SELECT project_id, project_name, COALESCE(description, ''), status_code "
        "FROM sec.project WHERE tenant_id = %s AND project_code = %s",
        (tenant_id, config.project_code),
        """
        INSERT INTO sec.project
            (tenant_id, project_code, project_name, description, status_code)
        VALUES (%s, %s, %s, %s, 'ACTIVE') RETURNING project_id
        """,
        (
            tenant_id,
            config.project_code,
            config.project_name,
            config.project_description or None,
        ),
        "project_id",
        (config.project_name, config.project_description, "ACTIVE"),
    )


def _environment(
    cursor: Any, config: SetupConfig, tenant_id: int
) -> tuple[int, bool]:
    return _find_or_insert(
        cursor,
        """
        SELECT environment_id, environment_name, environment_rank, status_code
        FROM sec.environment
        WHERE tenant_id = %s AND environment_code = %s
        """,
        (tenant_id, config.environment_code),
        """
        INSERT INTO sec.environment
            (tenant_id, environment_code, environment_name, environment_rank,
             status_code)
        VALUES (%s, %s, %s, %s, 'ACTIVE') RETURNING environment_id
        """,
        (
            tenant_id,
            config.environment_code,
            config.environment_name,
            config.environment_rank,
        ),
        "environment_id",
        (config.environment_name, config.environment_rank, "ACTIVE"),
    )


def _source_system(
    cursor: Any, config: SetupConfig, tenant_id: int, project_id: int
) -> tuple[int, bool]:
    return _find_or_insert(
        cursor,
        """
        SELECT system_id, system_name, COALESCE(description, ''), status_code
        FROM conn.source_system
        WHERE tenant_id = %s AND project_id = %s AND system_code = %s
        """,
        (tenant_id, project_id, config.system_code),
        """
        INSERT INTO conn.source_system
            (tenant_id, project_id, system_code, system_name, description, status_code)
        VALUES (%s, %s, %s, %s, %s, 'Active') RETURNING system_id
        """,
        (
            tenant_id,
            project_id,
            config.system_code,
            config.system_name,
            SYSTEM_DESCRIPTION,
        ),
        "system_id",
        (config.system_name, SYSTEM_DESCRIPTION, "Active"),
    )


def _credential(
    cursor: Any,
    tenant_id: int,
    endpoint: Endpoint,
    auth_method_id: int,
) -> tuple[int, bool]:
    return _find_or_insert(
        cursor,
        """
        SELECT credential_id, auth_method_id, secret_provider_code,
               secret_ref, status_code
        FROM conn.credential_ref
        WHERE tenant_id = %s AND credential_name = %s
        """,
        (tenant_id, endpoint.credential_name),
        """
        INSERT INTO conn.credential_ref
            (tenant_id, auth_method_id, credential_name, secret_provider_code,
             secret_ref, status_code)
        VALUES (%s, %s, %s, 'DEMO', %s, 'ACTIVE')
        RETURNING credential_id
        """,
        (tenant_id, auth_method_id, endpoint.credential_name, endpoint.secret_ref),
        "credential_id",
        (auth_method_id, "DEMO", endpoint.secret_ref, "ACTIVE"),
    )


def _profile(
    cursor: Any,
    tenant_id: int,
    system_id: int,
    environment_id: int,
    connector_version_id: int,
    credential_id: int,
    endpoint: Endpoint,
) -> tuple[int, bool]:
    compare = (
        tenant_id,
        environment_id,
        connector_version_id,
        credential_id,
        endpoint.host,
        endpoint.port,
        endpoint.database,
        endpoint.endpoint_url,
        endpoint.connect_timeout_seconds,
        endpoint.command_timeout_seconds,
        "ACTIVE",
    )
    return _find_or_insert(
        cursor,
        """
        SELECT connection_id, tenant_id, environment_id, connector_version_id,
               credential_id, host_name, port_no, database_name, endpoint_url,
               connect_timeout_seconds, command_timeout_seconds, status_code
        FROM conn.connection_profile
        WHERE system_id = %s AND environment_id = %s
          AND connection_role_code = %s AND connection_name = %s
        """,
        (system_id, environment_id, endpoint.role, endpoint.name),
        """
        INSERT INTO conn.connection_profile
            (tenant_id, system_id, environment_id, connector_version_id,
             credential_id, connection_role_code, connection_name, host_name,
             port_no, database_name, endpoint_url, connect_timeout_seconds,
             command_timeout_seconds, status_code)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE')
        RETURNING connection_id
        """,
        (
            tenant_id,
            system_id,
            environment_id,
            connector_version_id,
            credential_id,
            endpoint.role,
            endpoint.name,
            endpoint.host,
            endpoint.port,
            endpoint.database,
            endpoint.endpoint_url,
            endpoint.connect_timeout_seconds,
            endpoint.command_timeout_seconds,
        ),
        "connection_id",
        compare,
    )


def _parameters(cursor: Any, connection_id: int, endpoint: Endpoint) -> list[int]:
    parameter_ids: list[int] = []
    parameters = {
        "username": endpoint.username,
        "schema": endpoint.schema,
        "sslmode": endpoint.sslmode,
    }
    for name, value in parameters.items():
        cursor.execute(
            """
            SELECT connection_parameter_id, parameter_value, value_type_code,
                   is_secret_ref, environment_override
            FROM conn.connection_parameter
            WHERE connection_id = %s AND parameter_name = %s
            """,
            (connection_id, name),
        )
        existing = cursor.fetchone()
        if existing is not None:
            parameter_id, old_value, value_type, is_secret, override = existing
            if (old_value, value_type, is_secret, override) != (
                value,
                "STRING",
                False,
                False,
            ):
                raise ValueError(
                    f"Connection {connection_id} has a conflicting {name!r} "
                    "parameter; refusing to overwrite it."
                )
            parameter_ids.append(int(parameter_id))
            continue
        cursor.execute(
            """
            INSERT INTO conn.connection_parameter
                (connection_id, parameter_name, parameter_value, value_type_code,
                 is_secret_ref, environment_override)
            VALUES (%s, %s, %s, 'STRING', FALSE, FALSE)
            RETURNING connection_parameter_id
            """,
            (connection_id, name, value),
        )
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Database did not return a generated parameter ID.")
        parameter_ids.append(int(row[0]))
    return parameter_ids


def _secret_for(endpoint: Endpoint) -> str:
    secret = os.environ.get(endpoint.secret_env_var)
    if not secret:
        raise ConfigurationError(
            f"Required secret environment variable {endpoint.secret_env_var} "
            "is not set or is empty."
        )
    return secret


def _check_endpoint_privileges(connection: Any, endpoint: Endpoint) -> None:
    role = endpoint.role
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT current_database(), current_user,
                   has_database_privilege(current_user, current_database(), 'CONNECT'),
                   EXISTS (
                       SELECT 1 FROM information_schema.schemata
                       WHERE schema_name = %s
                   ),
                   has_schema_privilege(current_user, %s, 'USAGE'),
                   has_schema_privilege(current_user, %s, 'CREATE')
            """,
            (endpoint.schema, endpoint.schema, endpoint.schema),
        )
        database, username, can_connect, schema_exists, can_use, can_create = (
            cursor.fetchone()
        )
        if not can_connect:
            raise PermissionError(f"{role} user lacks CONNECT privilege.")
        if not schema_exists:
            raise LookupError(
                f"{role} database {database!r} has no schema {endpoint.schema!r}."
            )
        if not can_use:
            raise PermissionError(
                f"{role} user {username!r} lacks USAGE on schema {endpoint.schema!r}."
            )

        cursor.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = %s
            ORDER BY tablename
            """,
            (endpoint.schema,),
        )
        tables = [row[0] for row in cursor.fetchall()]
        required_privileges = (
            ("SELECT",) if role == "SOURCE" else ("SELECT", "INSERT")
        )
        missing: list[str] = []
        for table_name in tables:
            cursor.execute(
                """
                SELECT has_table_privilege(
                    current_user,
                    to_regclass(quote_ident(%s) || '.' || quote_ident(%s)),
                    %s
                )
                """,
                (endpoint.schema, table_name, required_privileges[0]),
            )
            if not cursor.fetchone()[0]:
                missing.append(f"{table_name}:{required_privileges[0]}")
            if role == "TARGET":
                cursor.execute(
                    """
                    SELECT has_table_privilege(
                        current_user,
                        to_regclass(quote_ident(%s) || '.' || quote_ident(%s)),
                        'INSERT'
                    )
                    """,
                    (endpoint.schema, table_name),
                )
                if not cursor.fetchone()[0]:
                    missing.append(f"{table_name}:INSERT")
        if missing:
            raise PermissionError(
                f"{role} user lacks required table privileges: "
                + ", ".join(missing)
            )
        if role == "TARGET" and not can_create:
            raise PermissionError(
                f"TARGET user lacks CREATE on schema {endpoint.schema!r}."
            )


def _validate_direct_endpoint(endpoint: Endpoint) -> None:
    secret = _secret_for(endpoint)
    try:
        with psycopg.connect(
            host=endpoint.host,
            port=endpoint.port,
            dbname=endpoint.database,
            user=endpoint.username,
            password=secret,
            sslmode=endpoint.sslmode,
            connect_timeout=endpoint.connect_timeout_seconds,
            options=f"-c statement_timeout={endpoint.command_timeout_seconds * 1000}",
            application_name="mdip_dynamic_connection_setup",
        ) as connection:
            _check_endpoint_privileges(connection, endpoint)
    except Exception as error:
        raise RuntimeError(
            f"{endpoint.role} connectivity/authentication/privilege validation "
            f"failed ({type(error).__name__}: {error}); verify the configured endpoint, "
            "credentials, schema, network access, SSL mode, and privileges."
        ) from error


def _create_metadata(config: SetupConfig) -> dict[str, Any]:
    ids: dict[str, Any] = {}
    with get_metastore_connection() as connection:
        try:
            with connection.cursor() as cursor:
                verify_schema(cursor)
                connector_id, connector_version_id, auth_method_id = (
                    validate_postgresql_connector(cursor)
                )
                tenant_id, tenant_created = _tenant(cursor, config)
                project_id, project_created = _project(
                    cursor, config, tenant_id
                )
                environment_id, environment_created = _environment(
                    cursor, config, tenant_id
                )
                system_id, system_created = _source_system(
                    cursor, config, tenant_id, project_id
                )
                source_credential_id, source_credential_created = _credential(
                    cursor, tenant_id, config.source, auth_method_id
                )
                target_credential_id, target_credential_created = _credential(
                    cursor, tenant_id, config.target, auth_method_id
                )
                source_connection_id, source_profile_created = _profile(
                    cursor,
                    tenant_id,
                    system_id,
                    environment_id,
                    connector_version_id,
                    source_credential_id,
                    config.source,
                )
                target_connection_id, target_profile_created = _profile(
                    cursor,
                    tenant_id,
                    system_id,
                    environment_id,
                    connector_version_id,
                    target_credential_id,
                    config.target,
                )
                source_parameter_ids = _parameters(
                    cursor, source_connection_id, config.source
                )
                target_parameter_ids = _parameters(
                    cursor, target_connection_id, config.target
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    ids.update(
        tenant_id=tenant_id,
        project_id=project_id,
        environment_id=environment_id,
        system_id=system_id,
        connector_id=connector_id,
        connector_version_id=connector_version_id,
        auth_method_id=auth_method_id,
        source_credential_id=source_credential_id,
        target_credential_id=target_credential_id,
        source_connection_id=source_connection_id,
        target_connection_id=target_connection_id,
        source_parameter_ids=source_parameter_ids,
        target_parameter_ids=target_parameter_ids,
        created={
            "tenant": tenant_created,
            "project": project_created,
            "environment": environment_created,
            "system": system_created,
            "source_credential": source_credential_created,
            "target_credential": target_credential_created,
            "source_profile": source_profile_created,
            "target_profile": target_profile_created,
        },
    )
    return ids


def _validate_saved_profile(
    connection_id: int, endpoint: Endpoint
) -> None:
    connector = RuntimeConnectionResolver().resolve(connection_id)
    if connector.metadata.connection_role_code != endpoint.role:
        raise RuntimeError(
            f"Saved profile {connection_id} has unexpected role "
            f"{connector.metadata.connection_role_code!r}."
        )
    try:
        connector.connect()
        connection = connector._require_connection()
        _check_endpoint_privileges(connection, endpoint)
    except Exception as error:
        if isinstance(error, (PermissionError, LookupError)):
            raise
        raise RuntimeError(
            f"Saved {endpoint.role} profile {connection_id} failed runtime "
            f"validation ({type(error).__name__}); metadata was committed, "
            "but this connection could not be verified."
        ) from error
    finally:
        connector.close()


def _print_setup_result(config: SetupConfig, ids: dict[str, Any]) -> None:
    print("\nMETADATA REGISTRATION")
    for label, key in (
        ("Tenant ID", "tenant_id"),
        ("Project ID", "project_id"),
        ("Environment ID", "environment_id"),
        ("Source system ID", "system_id"),
        ("Validated connector ID", "connector_id"),
        ("Connector version ID", "connector_version_id"),
        ("Password auth method ID", "auth_method_id"),
        ("Source credential ID", "source_credential_id"),
        ("Target credential ID", "target_credential_id"),
        ("Source connection ID", "source_connection_id"),
        ("Target connection ID", "target_connection_id"),
    ):
        print(f"{label}: {ids[key]}")
    print(f"Source parameter IDs: {', '.join(map(str, ids['source_parameter_ids']))}")
    print(f"Target parameter IDs: {', '.join(map(str, ids['target_parameter_ids']))}")
    print(
        "Source: "
        f"{config.source.host}:{config.source.port}/"
        f"{config.source.database} schema={config.source.schema}"
    )
    print(
        "Target: "
        f"{config.target.host}:{config.target.port}/"
        f"{config.target.database} schema={config.target.schema}"
    )
    for label, endpoint, connection_id in (
        ("Source", config.source, ids["source_connection_id"]),
        ("Target", config.target, ids["target_connection_id"]),
    ):
        _validate_saved_profile(connection_id, endpoint)
        print(f"{label} connection: VALIDATED (profile ID {connection_id})")


def setup(config: SetupConfig) -> dict[str, Any]:
    # Validate the environment-backed references and actual endpoints before
    # writing any metadata.
    _secret_for(config.source)
    _secret_for(config.target)
    _validate_direct_endpoint(config.source)
    _validate_direct_endpoint(config.target)
    ids = _create_metadata(config)
    _print_setup_result(config, ids)
    return ids


def inspect_configuration(config: SetupConfig) -> None:
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT t.tenant_id, p.project_id, e.environment_id, s.system_id,
                       cp.connection_id, cp.connection_role_code,
                       cp.connection_name, cp.host_name, cp.port_no,
                       cp.database_name, cp.status_code, cr.credential_id,
                       cr.credential_name, cr.secret_provider_code,
                       schema_param.parameter_value
                FROM sec.tenant t
                JOIN sec.project p
                  ON p.tenant_id = t.tenant_id AND p.project_code = %s
                JOIN sec.environment e
                  ON e.tenant_id = t.tenant_id AND e.environment_code = %s
                JOIN conn.source_system s
                  ON s.tenant_id = t.tenant_id AND s.project_id = p.project_id
                 AND s.system_code = %s
                JOIN conn.connection_profile cp
                  ON cp.system_id = s.system_id
                 AND cp.environment_id = e.environment_id
                JOIN conn.credential_ref cr ON cr.credential_id = cp.credential_id
                LEFT JOIN conn.connection_parameter schema_param
                  ON schema_param.connection_id = cp.connection_id
                 AND schema_param.parameter_name = 'schema'
                WHERE t.tenant_code = %s
                  AND cp.connection_name IN (%s, %s)
                ORDER BY cp.connection_role_code
                """,
                (
                    config.project_code,
                    config.environment_code,
                    config.system_code,
                    config.tenant_code,
                    config.source.name,
                    config.target.name,
                ),
            )
            rows = cursor.fetchall()
    if not rows:
        raise LookupError("No saved profiles match the supplied natural keys.")
    for row in rows:
        (
            tenant_id, project_id, environment_id, system_id, connection_id,
            role, name, host, port, database, status, credential_id,
            credential_name, provider, schema_name,
        ) = row
        print(
            f"{role} profile_id={connection_id} name={name!r} "
            f"endpoint={host}:{port}/{database} status={status} "
            f"credential_id={credential_id} credential_name={credential_name!r} "
            f"provider={provider} schema={schema_name}"
        )
        print(
            f"tenant_id={tenant_id} project_id={project_id} "
            f"environment_id={environment_id} system_id={system_id}"
        )


def validate_configuration(config: SetupConfig) -> None:
    """Resolve profile IDs by configured natural keys and test saved profiles."""
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT cp.connection_id, cp.connection_role_code
                FROM conn.connection_profile cp
                JOIN conn.source_system s ON s.system_id = cp.system_id
                JOIN sec.project p ON p.project_id = s.project_id
                JOIN sec.tenant t ON t.tenant_id = cp.tenant_id
                JOIN sec.environment e ON e.environment_id = cp.environment_id
                WHERE t.tenant_code = %s
                  AND p.project_code = %s
                  AND e.environment_code = %s
                  AND s.system_code = %s
                  AND cp.connection_name IN (%s, %s)
                  AND cp.status_code = 'ACTIVE'
                ORDER BY cp.connection_role_code
                """,
                (
                    config.tenant_code,
                    config.project_code,
                    config.environment_code,
                    config.system_code,
                    config.source.name,
                    config.target.name,
                ),
            )
            rows = cursor.fetchall()
    found = {role: int(connection_id) for connection_id, role in rows}
    for endpoint in (config.source, config.target):
        connection_id = found.get(endpoint.role)
        if connection_id is None:
            raise LookupError(
                f"No ACTIVE saved {endpoint.role} profile matches the "
                "configuration natural keys."
            )
        _validate_saved_profile(connection_id, endpoint)
        print(
            f"{endpoint.role} connection: VALIDATED "
            f"(profile ID {connection_id}, {endpoint.host}:{endpoint.port}/"
            f"{endpoint.database}, schema={endpoint.schema})"
        )


def inspect_schema() -> None:
    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            verify_schema(cursor)
            cursor.execute(
                """
                SELECT table_schema, table_name, ordinal_position, column_name,
                       data_type, is_nullable, column_default, identity_generation
                FROM information_schema.columns
                WHERE table_schema IN ('sec', 'conn')
                  AND table_name = ANY(%s)
                ORDER BY table_schema, table_name, ordinal_position
                """,
                ([table.rsplit(".", 1)[1] for table in REQUIRED_COLUMNS],),
            )
            for row in cursor.fetchall():
                print(" | ".join("" if item is None else str(item) for item in row))
            cursor.execute(
                """
                SELECT n.nspname, t.relname, c.conname,
                       pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_class t ON t.oid = c.conrelid
                JOIN pg_namespace n ON n.oid = t.relnamespace
                WHERE n.nspname IN ('sec', 'conn')
                  AND t.relname = ANY(%s)
                ORDER BY n.nspname, t.relname, c.conname
                """,
                ([table.rsplit(".", 1)[1] for table in REQUIRED_COLUMNS],),
            )
            for row in cursor.fetchall():
                print("CONSTRAINT | " + " | ".join(str(item) for item in row))


def _interactive_config() -> SetupConfig:
    return interactive_config()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dynamically register PostgreSQL SOURCE and TARGET profiles in the "
            "existing metadata database. Passwords are environment-backed."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command, help_text in (
        ("setup", "Validate endpoints and atomically register all metadata."),
        ("inspect", "Show IDs and safe details for configured saved profiles."),
        ("validate", "Connect through the saved runtime profiles and check grants."),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument(
            "--config",
            type=Path,
            help="JSON config file containing endpoint metadata and secret env names.",
        )
        command_parser.add_argument(
            "--non-interactive",
            action="store_true",
            help="Require --config and never prompt.",
        )
    subparsers.add_parser(
        "inspect-schema",
        help="Print the live metadata table columns and constraints (read-only).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect-schema":
            inspect_schema()
            return 0
        if args.non_interactive and args.config is None:
            parser.error("--non-interactive requires --config.")
        config = load_config(args.config) if args.config else _interactive_config()
        if args.command == "setup":
            setup(config)
        elif args.command == "inspect":
            inspect_configuration(config)
        elif args.command == "validate":
            validate_configuration(config)
        else:
            parser.error(f"Unknown command: {args.command}")
        return 0
    except (ConfigurationError, LookupError, PermissionError, RuntimeError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1
    except psycopg.Error as error:
        LOGGER.error(
            "Metadata database operation failed (%s). Check the metadata "
            "connection and database constraints.",
            type(error).__name__,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
