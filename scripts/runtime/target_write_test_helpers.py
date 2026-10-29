
"""Shared metadata-driven helpers for target write integration tests."""

import os
import uuid
from datetime import date, datetime
from decimal import Decimal

from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.context_resolver import RuntimeObjectResolver
from app.runtime.metadata_resolver import RuntimeMetadataResolver


def required_env_int(name: str) -> int:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Set the {name} environment variable before running this test."
        )
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer.") from exc
    if parsed <= 0:
        raise RuntimeError(f"{name} must be greater than zero.")
    return parsed


def resolve_target():
    """Resolve a single target from pipeline metadata."""
    pipeline_version_id = required_env_int(
        "MDIP_TEST_PIPELINE_VERSION_ID"
    )
    tenant_id = required_env_int("MDIP_TEST_TENANT_ID")
    environment_id = required_env_int("MDIP_TEST_ENVIRONMENT_ID")

    plans = RuntimeMetadataResolver().resolve_all(
        pipeline_version_id=pipeline_version_id
    )
    if not plans:
        raise RuntimeError("No tasks were resolved for the selected pipeline.")

    task_code = os.getenv("MDIP_TEST_TASK_CODE")
    if task_code:
        plans = [
            plan for plan in plans
            if plan.task.task_code == task_code
        ]
        if not plans:
            raise RuntimeError(
                f"No task with code {task_code!r} exists in this pipeline."
            )

    target_dataset_ids = {
        plan.mapping.target_dataset_id for plan in plans
    }
    if len(target_dataset_ids) != 1:
        raise RuntimeError(
            "The selected pipeline resolves to multiple target datasets. "
            "Set MDIP_TEST_TASK_CODE to select one task."
        )

    dataset_id = next(iter(target_dataset_ids))
    target_object = RuntimeObjectResolver().resolve(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    connector = RuntimeConnectionResolver().resolve(
        connection_id=target_object.connection_id
    )

    return connector, target_object


def quote_identifier(name: str) -> str:
    """Safely quote a PostgreSQL identifier."""
    return '"' + name.replace('"', '""') + '"'


def inspect_writable_columns(connection, target_object):
    """Discover target columns and identify required insert columns."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                is_identity,
                is_generated,
                ordinal_position
            FROM information_schema.columns
            WHERE table_catalog = %s
              AND table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (
                target_object.catalog_name,
                target_object.schema_name,
                target_object.object_name,
            ),
        )
        rows = cursor.fetchall()

    if not rows:
        raise RuntimeError(
            "No columns were discovered for the metadata-resolved target "
            f"{target_object.schema_name}.{target_object.object_name}."
        )

    # Column metadata tuple indexes are based on the SELECT above.
    writable = [
        {
            "name": row[0],
            "data_type": row[1].lower(),
            "nullable": row[2] == "YES",
            "default": row[3],
            "identity": row[4],
            "generated": row[5],
            "ordinal": row[6],
        }
        for row in rows
        if row[4] != "YES" and row[5] == "NEVER"
    ]

    if not writable:
        raise RuntimeError("No writable target columns were discovered.")

    required = [
        column for column in writable
        if not column["nullable"] and column["default"] is None
    ]

    text_types = {"text", "character varying", "character"}
    marker_candidates = [
        column for column in writable
        if column["data_type"] in text_types
    ]
    if not marker_candidates:
        raise RuntimeError(
            "The target has no supported text column for verifying "
            "temporary test records."
        )

    marker_column = marker_candidates[0]

    # Insert only required columns plus one text marker column.
    selected_by_name = {column["name"]: column for column in required}
    selected_by_name[marker_column["name"]] = marker_column
    selected = sorted(
        selected_by_name.values(),
        key=lambda column: column["ordinal"],
    )

    return selected, marker_column


def next_numeric_value(connection, target_object, column):
    """Choose values above the current maximum for numeric key-like fields."""
    qualified = (
        f"{quote_identifier(target_object.schema_name)}."
        f"{quote_identifier(target_object.object_name)}"
    )
    sql = (
        f"SELECT MAX({quote_identifier(column['name'])}) "
        f"FROM {qualified}"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql)
        result = cursor.fetchone()[0]

    return (result or 0) + 1


def build_test_rows(connection, target_object, columns, marker_column):
    """Build two synthetic rows from discovered target column metadata."""
    token = uuid.uuid4().hex
    marker_values = [
        f"MDIP_TEST_{token}_1",
        f"MDIP_TEST_{token}_2",
    ]

    numeric_types = {
        "smallint", "integer", "bigint",
        "numeric", "decimal", "real", "double precision",
    }
    numeric_starts = {
        column["name"]: next_numeric_value(
            connection, target_object, column
        )
        for column in columns
        if column["data_type"] in numeric_types
    }

    rows = []
    for row_index, marker in enumerate(marker_values, start=1):
        values = []

        for column in columns:
            name = column["name"]
            data_type = column["data_type"]

            if name == marker_column["name"]:
                value = marker
            elif data_type in {"text", "character varying", "character"}:
                value = f"MDIP synthetic test {token} row {row_index}"
            elif data_type in {"smallint", "integer", "bigint"}:
                value = numeric_starts[name] + row_index - 1
            elif data_type in {"numeric", "decimal", "real", "double precision"}:
                value = Decimal(row_index)
            elif data_type == "boolean":
                value = False
            elif data_type == "date":
                value = date.today()
            elif data_type.startswith("timestamp"):
                value = datetime.now()
            elif data_type == "uuid":
                value = uuid.uuid4()
            elif data_type == "json":
                value = "{}"
            elif data_type == "jsonb":
                value = "{}"
            else:
                raise RuntimeError(
                    f"Unsupported required test column type: "
                    f"{name} ({data_type})."
                )

            values.append(value)

        rows.append(tuple(values))

    return marker_values, rows


def verify_marker_count(
    connection, target_object, marker_column, marker_values
):
    qualified = (
        f"{quote_identifier(target_object.schema_name)}."
        f"{quote_identifier(target_object.object_name)}"
    )
    sql = (
        f"SELECT COUNT(*) FROM {qualified} "
        f"WHERE {quote_identifier(marker_column['name'])} IN (%s, %s)"
    )

    with connection.cursor() as cursor:
        cursor.execute(sql, tuple(marker_values))
        return cursor.fetchone()[0]
