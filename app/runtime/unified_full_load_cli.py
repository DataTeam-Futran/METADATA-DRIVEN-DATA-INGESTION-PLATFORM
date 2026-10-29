"""CLI for table discovery, catalog onboarding, mapping, and governed loads.

The onboarding phase writes catalog, mapping, execution, and pipeline
metadata as governed versions. Data movement is only delegated to PipelineOrchestrator
after the existing mapping-approval and pipeline-publication gates pass.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.db.metastore import get_metastore_connection
from app.runtime.multi_table_full_load_executor import (
    MultiTableFullLoadExecutor,
    TableSchemaPreparation,
)
from app.runtime.pipeline_orchestrator import PipelineOrchestrator
from app.runtime.selective_table_full_load_executor import (
    _format_table,
    parse_table_selection,
    render_discovery_report,
    render_selected_tables,
)
from app.services.connection_service import ConnectionService
from app.services.governance_lifecycle_service import GovernanceLifecycleService
from scripts.metadata.capture_dataset_schema import (
    calculate_schema_hash,
    complete_capture_run,
    create_capture_run,
    create_schema_version,
    get_next_schema_version_number,
    resolve_native_datatype_id,
    resolve_platform_id,
)

logger = logging.getLogger(__name__)


def _normalize_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize connector column metadata while retaining supported attributes."""
    normalized: list[dict[str, Any]] = []
    for column in columns:
        name = str(column.get("column_name", "")).strip()
        data_type = str(column.get("data_type", "")).strip()
        ordinal = column.get("ordinal_position", column.get("ordinal_no"))
        if not name or not data_type or ordinal is None:
            raise ValueError(
                "Column discovery must return a name, data type, and ordinal."
            )
        nullable = column.get("is_nullable")
        is_nullable = (
            nullable
            if isinstance(nullable, bool)
            else str(nullable).strip().upper() in {"YES", "TRUE", "1"}
        )
        normalized.append(
            {
                "ordinal_position": int(ordinal),
                "field_name": name,
                "field_name_normalized": name.casefold(),
                "source_datatype_text": data_type,
                "is_nullable": is_nullable,
                "default_expression": column.get("column_default"),
                "length_value": column.get("character_maximum_length"),
                "precision_value": column.get("numeric_precision"),
                "scale_value": column.get("numeric_scale"),
                "datetime_precision": column.get("datetime_precision"),
                "is_identity": bool(column.get("is_identity", False)),
                "is_generated": str(
                    column.get("is_generated", "NEVER")
                ).strip().upper()
                not in {"NEVER", "NO", "FALSE", "0", ""},
            }
        )
    return sorted(normalized, key=lambda item: item["ordinal_position"])


def _identifier_code(prefix: str, *parts: str) -> str:
    """Build deterministic metadata codes without using raw names as SQL."""
    source = "|".join(parts)
    slug = re.sub(r"[^A-Z0-9]+", "_", source.upper()).strip("_")[:35]
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()[:10].upper()
    return f"{prefix}_{slug}_{digest}"


def _config_hash(configuration: dict[str, Any]) -> str:
    canonical = json.dumps(
        configuration,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _create_or_find_binding(
    cursor: Any,
    *,
    role: str,
    connection_id: int,
    database_name: str | None,
    schema_name: str,
    table_name: str,
    tenant_id: int,
    project_id: int,
    environment_id: int,
) -> tuple[int, int]:
    """Resolve a table binding or create its catalog dataset and binding."""
    cursor.execute(
        """
        SELECT b.dataset_binding_id, b.dataset_id, d.tenant_id,
               d.project_id, d.dataset_role_code, d.status_code,
               b.status_code
        FROM catalog.dataset_binding AS b
        JOIN catalog.dataset AS d ON d.dataset_id = b.dataset_id
        WHERE b.tenant_id = %s
          AND b.connection_id = %s
          AND b.environment_id = %s
          AND COALESCE(b.schema_name, '') = %s
          AND b.object_name = %s
        FOR UPDATE;
        """,
        (
            tenant_id,
            connection_id,
            environment_id,
            schema_name,
            table_name,
        ),
    )
    existing = cursor.fetchone()
    if existing is not None:
        binding_id, dataset_id, bound_tenant, bound_project, bound_role, dataset_status, binding_status = existing
        if (
            bound_tenant != tenant_id
            or bound_project != project_id
            or bound_role != role
            or dataset_status != "ACTIVE"
            or binding_status != "ACTIVE"
        ):
            raise ValueError(
                f"Existing {role.lower()} binding for "
                f"{schema_name}.{table_name} conflicts with the requested "
                "tenant, project, role, or active status."
            )
        return int(dataset_id), int(binding_id)

    cursor.execute(
        """
        SELECT DISTINCT d.object_type_code, d.layer_code
        FROM catalog.dataset_binding AS b
        JOIN catalog.dataset AS d ON d.dataset_id = b.dataset_id
        WHERE d.tenant_id = %s
          AND d.project_id = %s
          AND d.dataset_role_code = %s
          AND b.connection_id = %s
          AND b.environment_id = %s
          AND d.status_code = 'ACTIVE'
          AND b.status_code = 'ACTIVE'
        ORDER BY d.object_type_code, d.layer_code;
        """,
        (
            tenant_id,
            project_id,
            role,
            connection_id,
            environment_id,
        ),
    )
    conventions = cursor.fetchall()
    if len(conventions) != 1:
        raise LookupError(
            f"Cannot determine the catalog object/layer convention for "
            f"{role.lower()} connection {connection_id}. Provision one "
            "active binding for this connection and scope, or resolve the "
            "ambiguous conventions before onboarding."
        )
    object_type_code, layer_code = conventions[0]

    dataset_code = _identifier_code(
        "SRC" if role == "SOURCE" else "TGT",
        str(connection_id),
        schema_name,
        table_name,
    )
    cursor.execute(
        """
        SELECT dataset_id, object_type_code, dataset_role_code, layer_code,
               status_code
        FROM catalog.dataset
        WHERE tenant_id = %s AND project_id = %s AND dataset_code = %s
        FOR UPDATE;
        """,
        (tenant_id, project_id, dataset_code),
    )
    existing_dataset = cursor.fetchone()
    if existing_dataset is None:
        cursor.execute(
            """
            INSERT INTO catalog.dataset (
                tenant_id, project_id, dataset_code, dataset_name,
                object_type_code, dataset_role_code, layer_code
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING dataset_id;
            """,
            (
                tenant_id,
                project_id,
                dataset_code,
                f"{role.title()} {schema_name}.{table_name}",
                object_type_code,
                role,
                layer_code,
            ),
        )
        dataset_row = cursor.fetchone()
        if dataset_row is None:
            raise RuntimeError("Catalog dataset creation returned no ID.")
        dataset_id = int(dataset_row[0])
    else:
        (
            dataset_id,
            existing_object_type,
            existing_role,
            existing_layer,
            existing_status,
        ) = existing_dataset
        if (
            existing_object_type != object_type_code
            or existing_role != role
            or existing_layer != layer_code
            or existing_status != "ACTIVE"
        ):
            raise ValueError(
                f"Existing catalog dataset code {dataset_code!r} conflicts "
                "with the required object type, role, layer, or status."
            )
        dataset_id = int(dataset_id)

    cursor.execute(
        """
        INSERT INTO catalog.dataset_binding (
            tenant_id, dataset_id, environment_id, connection_id,
            catalog_name, schema_name, object_name, object_name_normalized
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING dataset_binding_id;
        """,
        (
            tenant_id,
            dataset_id,
            environment_id,
            connection_id,
            database_name,
            schema_name,
            table_name,
            table_name.casefold(),
        ),
    )
    binding_row = cursor.fetchone()
    if binding_row is None:
        raise RuntimeError("Catalog binding creation returned no ID.")
    logger.info(
        "Registered %s catalog binding | connection_id=%s "
        "dataset_id=%s binding_id=%s object=%s.%s",
        role.lower(),
        connection_id,
        dataset_id,
        binding_row[0],
        schema_name,
        table_name,
    )
    return dataset_id, int(binding_row[0])


def _capture_schema_version(
    cursor: Any,
    *,
    tenant_id: int,
    dataset_id: int,
    binding_id: int,
    connector_version_id: int,
    connector_id: int,
    columns: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """Persist a discovered schema and return its generated field IDs."""
    normalized = _normalize_columns(columns)
    schema_hash = calculate_schema_hash(normalized)
    capture_id = create_capture_run(
        cursor,
        tenant_id,
        binding_id,
        connector_version_id,
    )
    cursor.execute(
        """
        SELECT schema_version_id
        FROM catalog.dataset_schema_version
        WHERE dataset_id = %s AND schema_hash = %s
        ORDER BY version_no DESC
        LIMIT 1
        FOR UPDATE;
        """,
        (dataset_id, schema_hash),
    )
    existing = cursor.fetchone()
    if existing is not None:
        complete_capture_run(cursor, capture_id)
        schema_version_id = int(existing[0])
    else:
        platform_id = resolve_platform_id(cursor, connector_id)
        version_number = get_next_schema_version_number(cursor, dataset_id)
        schema_version_id = create_schema_version(
            cursor,
            tenant_id,
            dataset_id,
            binding_id,
            capture_id,
            version_number,
            schema_hash,
            "DISCOVERED",
        )
        for column in normalized:
            native_type_id = resolve_native_datatype_id(
                cursor,
                platform_id,
                column["source_datatype_text"],
            )
            cursor.execute(
                """
                INSERT INTO catalog.dataset_field (
                    tenant_id, schema_version_id, ordinal_no, field_name,
                    field_name_normalized, native_datatype_id,
                    source_datatype_text, length_value, precision_value,
                    scale_value, is_nullable, default_expression,
                    is_identity, is_generated
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s)
                RETURNING field_id;
                """,
                (
                    tenant_id,
                    schema_version_id,
                    column["ordinal_position"],
                    column["field_name"],
                    column["field_name_normalized"],
                    native_type_id,
                    column["source_datatype_text"],
                    column["length_value"],
                    column["precision_value"],
                    column["scale_value"],
                    column["is_nullable"],
                    column["default_expression"],
                    column["is_identity"],
                    column["is_generated"],
                ),
            )
        complete_capture_run(cursor, capture_id)

    cursor.execute(
        """
        SELECT field_id, field_name, native_datatype_id, ordinal_no
        FROM catalog.dataset_field
        WHERE schema_version_id = %s AND tenant_id = %s
        ORDER BY ordinal_no;
        """,
        (schema_version_id, tenant_id),
    )
    fields = [
        {
            "field_id": int(row[0]),
            "field_name": row[1],
            "native_datatype_id": int(row[2]) if row[2] is not None else None,
            "ordinal_no": int(row[3]),
        }
        for row in cursor.fetchall()
    ]
    return schema_version_id, fields


def _resolve_mapping_set(cursor: Any, requested_id: int | None) -> int:
    """Use a requested mapping set or require one unambiguous PUBLISHED set."""
    if requested_id is not None:
        cursor.execute(
            """
            SELECT mapping_set_id
            FROM dtype.datatype_mapping_set
            WHERE mapping_set_id = %s AND status_code = 'PUBLISHED';
            """,
            (requested_id,),
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(
                f"Published datatype mapping set {requested_id} was not found."
            )
        return int(row[0])

    cursor.execute(
        """
        SELECT mapping_set_id
        FROM dtype.datatype_mapping_set
        WHERE status_code = 'PUBLISHED'
        ORDER BY version_no DESC, mapping_set_id DESC;
        """
    )
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise LookupError(
            "A unique published datatype mapping set was not found; "
            "provide --datatype-mapping-set-id."
        )
    return int(rows[0][0])


def _create_mapping_and_pipeline(
    cursor: Any,
    *,
    tenant_id: int,
    project_id: int,
    source_dataset_id: int,
    target_dataset_id: int,
    source_schema_version_id: int,
    target_schema_version_id: int,
    source_fields: list[dict[str, Any]],
    target_fields: list[dict[str, Any]],
    datatype_mapping_set_id: int,
    source_connection_id: int,
    target_connection_id: int,
    source_schema: str,
    target_schema: str,
    table_name: str,
    batch_size: int,
) -> dict[str, Any]:
    """Create/reuse a DRAFT direct mapping, execution config, and pipeline."""
    source_by_name = {field["field_name"]: field for field in source_fields}
    target_by_name = {field["field_name"]: field for field in target_fields}
    missing_target = [name for name in source_by_name if name not in target_by_name]
    if missing_target:
        raise ValueError(
            "Target catalog schema is missing source fields: "
            + ", ".join(missing_target)
        )
    for name, source_field in source_by_name.items():
        target_field = target_by_name[name]
        if (
            source_field["native_datatype_id"] is not None
            and target_field["native_datatype_id"] is not None
            and source_field["native_datatype_id"]
            != target_field["native_datatype_id"]
        ):
            raise ValueError(
                f"Field {name!r} has different source and target native "
                "datatypes. Configure an explicit datatype conversion "
                "before publishing this direct mapping."
            )

    mapping_code = _identifier_code(
        "FULL",
        str(source_connection_id),
        source_schema,
        str(target_connection_id),
        target_schema,
        table_name,
    )
    configuration = {
        "tenant_id": tenant_id,
        "project_id": project_id,
        "source_dataset_id": source_dataset_id,
        "target_dataset_id": target_dataset_id,
        "source_schema_version_id": source_schema_version_id,
        "target_schema_version_id": target_schema_version_id,
        "datatype_mapping_set_id": datatype_mapping_set_id,
        "strategy": "TRUNCATE_INSERT",
        "fields": [
            [name, source_by_name[name]["field_id"], target_by_name[name]["field_id"]]
            for name in source_by_name
        ],
    }
    mapping_hash = _config_hash(configuration)

    cursor.execute(
        """
        SELECT mapping_id
        FROM map.mapping
        WHERE tenant_id = %s AND project_id = %s AND mapping_code = %s
        FOR UPDATE;
        """,
        (tenant_id, project_id, mapping_code),
    )
    mapping_row = cursor.fetchone()
    if mapping_row is None:
        cursor.execute(
            """
            INSERT INTO map.mapping (
                tenant_id, project_id, mapping_code, mapping_name,
                business_purpose, is_template, status_code
            )
            VALUES (%s, %s, %s, %s, %s, FALSE, 'DRAFT')
            RETURNING mapping_id;
            """,
            (
                tenant_id,
                project_id,
                mapping_code,
                f"Full load {source_schema}.{table_name}",
                f"Direct full-load mapping to {target_schema}.{table_name}.",
            ),
        )
        mapping_id = int(cursor.fetchone()[0])
    else:
        mapping_id = int(mapping_row[0])

    cursor.execute(
        """
        SELECT mapping_version_id, status_code
        FROM map.mapping_version
        WHERE mapping_id = %s AND config_hash = %s
        ORDER BY version_no DESC
        LIMIT 1
        FOR UPDATE;
        """,
        (mapping_id, mapping_hash),
    )
    version_row = cursor.fetchone()
    if version_row is not None:
        mapping_version_id = int(version_row[0])
        mapping_status = str(version_row[1])
        created = False
    else:
        cursor.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 "
            "FROM map.mapping_version WHERE mapping_id = %s;",
            (mapping_id,),
        )
        mapping_version_no = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO map.mapping_version (
                tenant_id, mapping_id, version_no,
                primary_source_dataset_id,
                primary_source_schema_version_id, target_dataset_id,
                target_schema_version_id, datatype_mapping_set_id,
                load_type_code, load_strategy_code, status_code, config_hash
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    'FULL', 'TRUNCATE_INSERT', 'DRAFT', %s)
            RETURNING mapping_version_id;
            """,
            (
                tenant_id,
                mapping_id,
                mapping_version_no,
                source_dataset_id,
                source_schema_version_id,
                target_dataset_id,
                target_schema_version_id,
                datatype_mapping_set_id,
                mapping_hash,
            ),
        )
        mapping_version_id = int(cursor.fetchone()[0])
        mapping_status = "DRAFT"
        created = True
        cursor.execute(
            """
            INSERT INTO map.mapping_source (
                tenant_id, mapping_version_id, dataset_id, schema_version_id,
                source_alias, sequence_no, is_primary
            )
            VALUES (%s, %s, %s, %s, 'src', 1, TRUE);
            """,
            (
                tenant_id,
                mapping_version_id,
                source_dataset_id,
                source_schema_version_id,
            ),
        )
        for source_name, source_field in source_by_name.items():
            target_field = target_by_name[source_name]
            cursor.execute(
                """
                INSERT INTO map.mapping_field (
                    tenant_id, mapping_version_id, target_field_id,
                    mapping_type_code, null_rule_code, key_role_code,
                    scd_behavior_code, ordinal_no
                )
                VALUES (%s, %s, %s, 'DIRECT', 'KEEP', 'NONE', 'NA', %s)
                RETURNING mapping_field_id;
                """,
                (
                    tenant_id,
                    mapping_version_id,
                    target_field["field_id"],
                    source_field["ordinal_no"],
                ),
            )
            mapping_field_id = int(cursor.fetchone()[0])
            cursor.execute(
                """
                INSERT INTO map.mapping_field_input (
                    tenant_id, mapping_field_id, source_field_id,
                    source_alias, input_role_code, ordinal_no
                )
                VALUES (%s, %s, %s, 'src', 'PRIMARY', 1);
                """,
                (tenant_id, mapping_field_id, source_field["field_id"]),
            )
        cursor.execute(
            """
            INSERT INTO ingest.load_config (
                mapping_version_id, load_type_code, batch_size,
                truncate_before_load, is_active
            )
            VALUES (%s, 'FULL_LOAD', %s, TRUE, TRUE);
            """,
            (mapping_version_id, batch_size),
        )
        cursor.execute(
            """
            INSERT INTO ingest.target_load_config (
                mapping_version_id, tenant_id, load_method_code, commit_size,
                auto_create_target, alter_target_policy_code,
                transaction_mode_code, write_timeout_seconds,
                target_prepare_action_code, target_schema_policy_code,
                constraint_apply_policy_code, index_apply_policy_code
            )
            VALUES (
                %s, %s, 'AUTO', NULL, FALSE, 'BLOCK', 'AUTO', 600,
                'TRUNCATE', 'CREATE_IF_MISSING',
                'APPLY_AFTER_LOAD', 'APPLY_AFTER_LOAD'
            );
            """,
            (mapping_version_id, tenant_id),
        )

    pipeline_code = _identifier_code("FULL_PIPELINE", mapping_code)
    cursor.execute(
        """
        SELECT pipeline_id
        FROM orch.pipeline
        WHERE tenant_id = %s AND project_id = %s AND pipeline_code = %s
        FOR UPDATE;
        """,
        (tenant_id, project_id, pipeline_code),
    )
    pipeline_row = cursor.fetchone()
    if pipeline_row is None:
        cursor.execute(
            """
            INSERT INTO orch.pipeline (
                tenant_id, project_id, pipeline_code, pipeline_name,
                status_code, pipeline_type_code
            )
            VALUES (%s, %s, %s, %s, 'ACTIVE', 'BATCH_MIGRATION')
            RETURNING pipeline_id;
            """,
            (
                tenant_id,
                project_id,
                pipeline_code,
                f"Full load {source_schema}.{table_name}",
            ),
        )
        pipeline_id = int(cursor.fetchone()[0])
    else:
        pipeline_id = int(pipeline_row[0])

    cursor.execute(
        """
        SELECT pv.pipeline_version_id, pv.status_code
        FROM orch.pipeline_version AS pv
        JOIN orch.pipeline_task AS pt
          ON pt.pipeline_version_id = pv.pipeline_version_id
        WHERE pv.pipeline_id = %s AND pt.mapping_version_id = %s
        ORDER BY pv.version_no DESC
        LIMIT 1
        FOR UPDATE OF pv;
        """,
        (pipeline_id, mapping_version_id),
    )
    pipeline_version_row = cursor.fetchone()
    if pipeline_version_row is None:
        cursor.execute(
            "SELECT COALESCE(MAX(version_no), 0) + 1 "
            "FROM orch.pipeline_version WHERE pipeline_id = %s;",
            (pipeline_id,),
        )
        pipeline_version_no = int(cursor.fetchone()[0])
        pipeline_hash = _config_hash(
            {
                "pipeline_code": pipeline_code,
                "mapping_version_id": mapping_version_id,
                "load_strategy": "TRUNCATE_INSERT",
            }
        )
        cursor.execute(
            """
            INSERT INTO orch.pipeline_version (
                tenant_id, pipeline_id, version_no, status_code, config_hash
            )
            VALUES (%s, %s, %s, 'DRAFT', %s)
            RETURNING pipeline_version_id;
            """,
            (tenant_id, pipeline_id, pipeline_version_no, pipeline_hash),
        )
        pipeline_version_id = int(cursor.fetchone()[0])
        pipeline_status = "DRAFT"
        cursor.execute(
            """
            INSERT INTO orch.pipeline_task (
                tenant_id, pipeline_version_id, task_code, task_name,
                task_type_code, mapping_version_id, sequence_no,
                on_failure_code, retry_policy_id, timeout_seconds, task_config
            )
            VALUES (%s, %s, %s, %s, 'FULL_LOAD', %s, 1, 'STOP',
                    NULL, 600, NULL);
            """,
            (
                tenant_id,
                pipeline_version_id,
                _identifier_code("FULL_LOAD", table_name),
                f"Full load {source_schema}.{table_name}",
                mapping_version_id,
            ),
        )
    else:
        pipeline_version_id = int(pipeline_version_row[0])
        pipeline_status = str(pipeline_version_row[1])

    return {
        "mapping_id": mapping_id,
        "mapping_version_id": mapping_version_id,
        "mapping_status": mapping_status,
        "pipeline_id": pipeline_id,
        "pipeline_version_id": pipeline_version_id,
        "pipeline_status": pipeline_status,
        "mapping_created": created,
        "column_count": len(source_by_name),
    }


def _onboard_table(
    *,
    source_metadata: Any,
    target_metadata: Any,
    source_columns: list[dict[str, Any]],
    target_columns: list[dict[str, Any]],
    source_schema: str,
    target_schema: str,
    table_name: str,
    tenant_id: int,
    project_id: int,
    environment_id: int,
    batch_size: int,
    datatype_mapping_set_id: int | None,
) -> dict[str, Any]:
    """Persist bindings, schema versions, mapping, and a DRAFT pipeline atomically."""
    source_names = [
        column["column_name"]
        for column in sorted(
            source_columns,
            key=lambda item: item.get(
                "ordinal_position",
                item.get("ordinal_no", 0),
            ),
        )
    ]
    target_names = {
        column["column_name"] for column in target_columns
    }
    if any(name not in target_names for name in source_names):
        raise ValueError(
            "Target schema metadata is missing source columns after target "
            "preparation; mapping metadata was not persisted."
        )

    with get_metastore_connection() as connection:
        try:
            with connection.cursor() as cursor:
                mapping_set_id = _resolve_mapping_set(
                    cursor,
                    datatype_mapping_set_id,
                )
                source_dataset_id, source_binding_id = _create_or_find_binding(
                    cursor,
                    role="SOURCE",
                    connection_id=source_metadata.connection_id,
                    database_name=source_metadata.database_name,
                    schema_name=source_schema,
                    table_name=table_name,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    environment_id=environment_id,
                )
                target_dataset_id, target_binding_id = _create_or_find_binding(
                    cursor,
                    role="TARGET",
                    connection_id=target_metadata.connection_id,
                    database_name=target_metadata.database_name,
                    schema_name=target_schema,
                    table_name=table_name,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    environment_id=environment_id,
                )
                source_schema_version_id, source_fields = _capture_schema_version(
                    cursor,
                    tenant_id=tenant_id,
                    dataset_id=source_dataset_id,
                    binding_id=source_binding_id,
                    connector_version_id=source_metadata.connector_version_id,
                    connector_id=source_metadata.connector_id,
                    columns=source_columns,
                )
                target_schema_version_id, target_fields = _capture_schema_version(
                    cursor,
                    tenant_id=tenant_id,
                    dataset_id=target_dataset_id,
                    binding_id=target_binding_id,
                    connector_version_id=target_metadata.connector_version_id,
                    connector_id=target_metadata.connector_id,
                    columns=target_columns,
                )
                result = _create_mapping_and_pipeline(
                    cursor,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    source_dataset_id=source_dataset_id,
                    target_dataset_id=target_dataset_id,
                    source_schema_version_id=source_schema_version_id,
                    target_schema_version_id=target_schema_version_id,
                    source_fields=source_fields,
                    target_fields=target_fields,
                    datatype_mapping_set_id=mapping_set_id,
                    source_connection_id=source_metadata.connection_id,
                    target_connection_id=target_metadata.connection_id,
                    source_schema=source_schema,
                    target_schema=target_schema,
                    table_name=table_name,
                    batch_size=batch_size,
                )
                result.update(
                    {
                        "source_dataset_id": source_dataset_id,
                        "target_dataset_id": target_dataset_id,
                        "source_schema_version_id": source_schema_version_id,
                        "target_schema_version_id": target_schema_version_id,
                        "source_binding_id": source_binding_id,
                        "target_binding_id": target_binding_id,
                        "datatype_mapping_set_id": mapping_set_id,
                        "source_fields": source_fields,
                        "target_fields": target_fields,
                    }
                )
            connection.commit()
            return result
        except Exception:
            connection.rollback()
            logger.exception(
                "Metadata onboarding transaction rolled back for %s.%s.",
                source_schema,
                table_name,
            )
            raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover source tables, create missing target/catalog metadata, "
            "persist DRAFT mappings, and execute only after governance approval."
        )
    )
    parser.add_argument(
        "--source-connection-id",
        type=int,
        help="Configured source profile ID; prompted when omitted.",
    )
    parser.add_argument(
        "--target-connection-id",
        type=int,
        help="Configured target profile ID; prompted when omitted.",
    )
    parser.add_argument(
        "--source-schema",
        help="Source schema to discover; prompted when omitted.",
    )
    parser.add_argument(
        "--target-schema",
        help="Target schema to prepare; prompted when omitted.",
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        help="Tenant scope ID; inferred from active bindings when possible.",
    )
    parser.add_argument(
        "--project-id",
        type=int,
        help="Project scope ID; inferred from active bindings when possible.",
    )
    parser.add_argument(
        "--environment-id",
        type=int,
        help="Environment scope ID; inferred from active bindings when possible.",
    )
    parser.add_argument(
        "--datatype-mapping-set-id",
        type=int,
        help="Published datatype mapping set. Auto-resolved only when unique.",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        help="ALL, or one or more discovered source table names/indexes.",
    )
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--auto-governance",
        action="store_true",
        help=(
            "Apply the explicit development-only governance workflow. "
            "Production environments are always blocked."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Request a load after onboarding without an interactive confirmation.",
    )
    return parser


def _select_tables(
    requested: list[str] | None,
    discovered: list[str],
) -> list[str]:
    if requested is None:
        print("\nTABLE LOAD SCOPE")
        print("  1. ALL discovered tables")
        print("  2. Select specific tables")
        while True:
            try:
                mode = input("Choose 1 or 2: ").strip()
            except (EOFError, OSError) as exc:
                raise ValueError(
                    "Table selection was not provided; use --tables."
                ) from exc
            if mode == "1":
                return list(discovered)
            if mode == "2":
                try:
                    selection = input(
                        "Enter table numbers or names, comma separated: "
                    ).strip()
                except (EOFError, OSError) as exc:
                    raise ValueError(
                        "Selected tables were not provided; use --tables."
                    ) from exc
                return parse_table_selection(selection, discovered)
            print("Invalid choice. Enter 1 for ALL or 2 for selected tables.")
    if any(value.strip().upper() == "ALL" for value in requested):
        if len(requested) != 1:
            raise ValueError("ALL cannot be combined with individual tables.")
        return list(discovered)
    return parse_table_selection(",".join(requested), discovered)


def _resolve_scope_from_bindings(args: argparse.Namespace) -> bool:
    """Infer a unique tenant/project/environment from active connection bindings."""
    scope_attributes = ("tenant_id", "project_id", "environment_id")
    missing = [
        attribute
        for attribute in scope_attributes
        if getattr(args, attribute) is None
    ]
    if not missing:
        return False

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT source_dataset.tenant_id,
                                source_dataset.project_id,
                                source_binding.environment_id
                FROM catalog.dataset_binding AS source_binding
                JOIN catalog.dataset AS source_dataset
                  ON source_dataset.dataset_id = source_binding.dataset_id
                JOIN catalog.dataset_binding AS target_binding
                  ON target_binding.tenant_id = source_binding.tenant_id
                 AND target_binding.environment_id = source_binding.environment_id
                JOIN catalog.dataset AS target_dataset
                  ON target_dataset.dataset_id = target_binding.dataset_id
                 AND target_dataset.tenant_id = source_dataset.tenant_id
                 AND target_dataset.project_id = source_dataset.project_id
                WHERE source_binding.connection_id = %s
                  AND target_binding.connection_id = %s
                  AND source_dataset.dataset_role_code = 'SOURCE'
                  AND target_dataset.dataset_role_code = 'TARGET'
                  AND source_binding.status_code = 'ACTIVE'
                  AND target_binding.status_code = 'ACTIVE'
                  AND source_dataset.status_code = 'ACTIVE'
                  AND target_dataset.status_code = 'ACTIVE'
                ORDER BY source_dataset.tenant_id,
                         source_dataset.project_id,
                         source_binding.environment_id;
                """,
                (args.source_connection_id, args.target_connection_id),
            )
            candidates = cursor.fetchall()

    if len(candidates) == 1:
        inferred = dict(zip(scope_attributes, candidates[0], strict=True))
        for attribute in missing:
            setattr(args, attribute, int(inferred[attribute]))
        if any(
            getattr(args, attribute) is not None
            and int(getattr(args, attribute)) != int(inferred[attribute])
            for attribute in scope_attributes
        ):
            raise ValueError(
                "The supplied tenant/project/environment scope conflicts "
                "with the unique active catalog bindings for these connections."
            )
        print(
            "Resolved catalog scope from active connection bindings: "
            f"tenant={inferred['tenant_id']} "
            f"project={inferred['project_id']} "
            f"environment={inferred['environment_id']}"
        )
        return True

    if not candidates:
        print(
            "Could not infer scope: no matching active source/target catalog "
            "bindings were found."
        )
    else:
        print(
            "Could not infer a unique scope: multiple active source/target "
            "binding scopes were found."
        )
    return False


def _prompt_for_missing_arguments(args: argparse.Namespace) -> None:
    """Prompt for connection and schema arguments omitted on the CLI."""
    prompts = (
        ("source_connection_id", "Source connection ID", int),
        ("target_connection_id", "Target connection ID", int),
        ("source_schema", "Source schema", str),
        ("target_schema", "Target schema", str),
    )
    for attribute, label, value_type in prompts:
        if getattr(args, attribute) is not None:
            continue
        flag = "--" + attribute.replace("_", "-")
        try:
            value = input(f"{label} (or provide {flag}): ").strip()
        except (EOFError, OSError) as exc:
            raise ValueError(
                f"{flag} is required when running non-interactively."
            ) from exc
        if not value:
            raise ValueError(
                f"{label} cannot be empty; provide {flag} or enter a value."
            )
        try:
            setattr(args, attribute, value_type(value))
        except ValueError as exc:
            raise ValueError(
                f"{label} must be a valid "
                f"{'integer' if value_type is int else 'value'}."
            ) from exc


def _prompt_for_missing_scope(args: argparse.Namespace) -> None:
    """Prompt for any scope value not resolved from catalog bindings."""
    for attribute, label in (
        ("tenant_id", "Tenant ID"),
        ("project_id", "Project ID"),
        ("environment_id", "Environment ID"),
    ):
        if getattr(args, attribute) is not None:
            continue
        flag = "--" + attribute.replace("_", "-")
        try:
            value = input(f"{label} (or provide {flag}): ").strip()
        except (EOFError, OSError) as exc:
            raise ValueError(
                f"{flag} is required when no unique active catalog scope "
                "can be resolved and the command is running non-interactively."
            ) from exc
        if not value:
            raise ValueError(
                f"{label} cannot be empty; provide {flag} or enter a value."
            )
        try:
            setattr(args, attribute, int(value))
        except ValueError as exc:
            raise ValueError(f"{label} must be a valid integer.") from exc


def _prompt_for_load_confirmation() -> bool:
    """Ask before loading when the caller did not pass --execute."""
    while True:
        try:
            answer = input(
                "\nStart the full load now? This uses the configured "
                "truncate-and-insert strategy [y/N]: "
            ).strip().casefold()
        except (EOFError, OSError):
            return False
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        print("Enter y or n.")


def _print_connection(role: str, metadata: Any) -> None:
    """Print non-secret connection profile fields only."""
    endpoint = "-"
    if metadata.endpoint_url:
        parsed_endpoint = urlsplit(metadata.endpoint_url)
        endpoint = parsed_endpoint.scheme + "://" + (
            parsed_endpoint.hostname or ""
        )
        if parsed_endpoint.port is not None:
            endpoint += f":{parsed_endpoint.port}"
        endpoint += parsed_endpoint.path
    print(
        f"{role}: id={metadata.connection_id} "
        f"name={metadata.connection_name} "
        f"connector={metadata.connector_code} "
        f"host={metadata.host_name or '-'} "
        f"port={metadata.port_no or '-'} "
        f"database={metadata.database_name or '-'} "
        f"endpoint={endpoint}"
    )


def _print_onboarding(results: list[dict[str, Any]]) -> None:
    rows = [
        [
            result["table_name"],
            str(result.get("source_dataset_id", "-")),
            str(result.get("target_dataset_id", "-")),
            str(result.get("mapping_version_id", "-")),
            str(result.get("mapping_status", "Failed")),
            str(result.get("pipeline_version_id", "-")),
            str(result.get("pipeline_status", "-")),
            result.get("error", ""),
        ]
        for result in results
    ]
    print("\nMETADATA ONBOARDING")
    for line in _format_table(
        [
            "Table",
            "Source Dataset",
            "Target Dataset",
            "Mapping Version",
            "Mapping Status",
            "Pipeline Version",
            "Pipeline Status",
            "Details",
        ],
        rows or [["-", "-", "-", "-", "-", "-", "-", "No onboarding attempted"]],
    ):
        print(line)
    for result in results:
        fields = result.get("source_fields")
        target_by_name = {
            field["field_name"]: field
            for field in result.get("target_fields", [])
        }
        if not fields:
            continue
        print(f"\nCOLUMN MAPPING: {result['table_name']}")
        for line in _format_table(
            [
                "Source Field",
                "Target Field",
                "Source Field ID",
                "Target Field ID",
            ],
            [
                [
                    source_field["field_name"],
                    target_by_name.get(
                        source_field["field_name"], {}
                    ).get("field_name", "UNMAPPED"),
                    str(source_field["field_id"]),
                    str(
                        target_by_name.get(
                            source_field["field_name"], {}
                        ).get("field_id", "-")
                    ),
                ]
                for source_field in fields
            ],
        ):
            print(line)


def _print_target_preparation(
    preparations: list[TableSchemaPreparation],
    target_schema: str,
) -> None:
    rows = [
        [
            f"{target_schema}.{item.table_name}",
            "Created" if item.target_was_created and not item.error_details else (
                "Exists" if not item.target_was_created else "Failed"
            ),
            item.schema_validation_status,
            item.load_compatibility_status,
            item.error_details or "",
        ]
        for item in preparations
    ]
    print("\nTARGET TABLE PREPARATION AND SCHEMA VALIDATION")
    for line in _format_table(
        ["Target Table", "Existence", "Schema", "Load Compatibility", "Details"],
        rows or [["-", "-", "Not checked", "Not checked", "No target tables prepared"]],
    ):
        print(line)
    for item in preparations:
        if not item.source_columns:
            continue
        target_by_name = {
            column["column_name"]: column
            for column in item.target_columns
        }
        source_rows = [
            [
                str(column.get("ordinal_position", column.get("ordinal_no", ""))),
                column["column_name"],
                str(column.get("data_type", "")),
                str(column.get("is_nullable", "")),
                str(
                    target_by_name.get(column["column_name"], {}).get(
                        "data_type",
                        "MISSING",
                    )
                ),
                str(
                    target_by_name.get(column["column_name"], {}).get(
                        "is_nullable",
                        "MISSING",
                    )
                ),
            ]
            for column in item.source_columns
        ]
        print(f"\nSOURCE/TARGET METADATA: {item.table_name}")
        for line in _format_table(
            [
                "#",
                "Source Field",
                "Source Type",
                "Source Nullable",
                "Target Type",
                "Target Nullable",
            ],
            source_rows,
        ):
            print(line)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        _prompt_for_missing_arguments(args)
        _resolve_scope_from_bindings(args)
        _prompt_for_missing_scope(args)
    except ValueError as exc:
        parser.error(str(exc))
    if min(
        args.source_connection_id,
        args.target_connection_id,
        args.tenant_id,
        args.project_id,
        args.environment_id,
        args.batch_size,
    ) <= 0:
        parser.error("Connection, scope IDs, and batch size must be positive.")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        connection_service = ConnectionService()
        source_metadata = connection_service.get_connection_metadata(
            args.source_connection_id
        )
        target_metadata = connection_service.get_connection_metadata(
            args.target_connection_id
        )
        if source_metadata.connection_role_code not in {"SOURCE", "BOTH"}:
            raise ValueError("Configured source connection is not SOURCE/BOTH.")
        if target_metadata.connection_role_code not in {"TARGET", "BOTH"}:
            raise ValueError("Configured target connection is not TARGET/BOTH.")

        print("CONNECTION PROFILES")
        _print_connection("Source", source_metadata)
        _print_connection("Target", target_metadata)

        executor = MultiTableFullLoadExecutor(
            source_connection_id=args.source_connection_id,
            target_connection_id=args.target_connection_id,
            batch_size=args.batch_size,
        )
        discovered = executor.discover_source_tables(args.source_schema)
        print()
        print(render_discovery_report(args.source_schema, discovered))
        if not discovered:
            raise LookupError(
                f"No source tables found in schema {args.source_schema!r}."
            )
        selected = _select_tables(args.tables, discovered)
        print()
        print(render_selected_tables(selected))

        preparations = executor.prepare_target_tables(
            args.source_schema,
            args.target_schema,
            selected,
        )
        _print_target_preparation(preparations, args.target_schema)
        prep_by_table = {item.table_name: item for item in preparations}
        onboarding: list[dict[str, Any]] = []
        executable: list[dict[str, Any]] = []
        for table_name in selected:
            prep: TableSchemaPreparation = prep_by_table[table_name]
            if prep.error_details or not prep.target_columns:
                onboarding.append(
                    {
                        "table_name": table_name,
                        "error": prep.error_details or "Target metadata unavailable.",
                    }
                )
                continue
            try:
                metadata = _onboard_table(
                    source_metadata=source_metadata,
                    target_metadata=target_metadata,
                    source_columns=prep.source_columns,
                    target_columns=prep.target_columns,
                    source_schema=args.source_schema,
                    target_schema=args.target_schema,
                    table_name=table_name,
                    tenant_id=args.tenant_id,
                    project_id=args.project_id,
                    environment_id=args.environment_id,
                    batch_size=args.batch_size,
                    datatype_mapping_set_id=args.datatype_mapping_set_id,
                )
                metadata["table_name"] = table_name
                try:
                    governance = GovernanceLifecycleService().activate_and_publish(
                        tenant_id=args.tenant_id,
                        project_id=args.project_id,
                        environment_id=args.environment_id,
                        mapping_version_id=int(metadata["mapping_version_id"]),
                        pipeline_version_id=int(metadata["pipeline_version_id"]),
                        auto_governance=True if args.auto_governance else None,
                    )
                    metadata["mapping_status"] = governance.mapping_status
                    metadata["pipeline_status"] = governance.pipeline_status
                    metadata["governance_reason"] = governance.reason
                except Exception as exc:
                    logger.warning("Governance transition blocked for %s: %s", table_name, exc)
                    metadata["governance_error"] = f"{type(exc).__name__}: {exc}"
                onboarding.append(metadata)
                if (
                    metadata["mapping_status"].upper() == "ACTIVE"
                    and metadata["pipeline_status"].upper() == "PUBLISHED"
                ):
                    executable.append(metadata)
            except Exception as exc:
                logger.exception("Onboarding failed for table %s.", table_name)
                onboarding.append(
                    {
                        "table_name": table_name,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        _print_onboarding(onboarding)
        if any(result.get("error") for result in onboarding):
            print(
                "\nOne or more tables could not be onboarded. "
                "Other selected tables were processed independently."
            )
        load_requested = args.execute
        if not load_requested:
            load_requested = _prompt_for_load_confirmation()
        if not load_requested:
            print(
                "\nNo data was loaded. Metadata onboarding is complete. "
                "The mapping must be ACTIVE and pipeline PUBLISHED before "
                "a load can run; an interactive confirmation or --execute "
                "does not bypass those governance checks."
            )
            return 1 if any(result.get("error") for result in onboarding) else 0

        blocked = [
            result
            for result in onboarding
            if not result.get("error")
            and result not in executable
        ]
        if blocked:
            blocked_rows = [
                [
                    result["table_name"],
                    str(result.get("mapping_status", "Unknown")),
                    str(result.get("pipeline_status", "Unknown")),
                ]
                for result in blocked
            ]
            print(
                "\nLOAD BLOCKED: approval/publication is required. "
                "No truncate or insert was attempted."
            )
            for line in _format_table(
                ["Table", "Mapping Status (required: ACTIVE)", "Pipeline Status (required: PUBLISHED)"],
                blocked_rows,
            ):
                print(line)
            print(
                "Use the approved governance process to activate these "
                "mapping versions and publish their pipeline versions, then "
                "rerun this command with --execute."
            )
        if not executable:
            return 1 if blocked or any(result.get("error") for result in onboarding) else 0

        orchestrator = PipelineOrchestrator()
        execution_errors = False
        execution_summary: list[dict[str, Any]] = []
        for result in executable:
            rows_written = 0
            pipeline_status = "FAILED"
            error_details = ""
            try:
                previous_logging_disable_level = logging.root.manager.disable
                with contextlib.redirect_stdout(io.StringIO()) :
                    logging.disable(logging.CRITICAL)
                    try:
                        run_results = orchestrator.execute_pipeline(
                            pipeline_version_id=result["pipeline_version_id"],
                            tenant_id=args.tenant_id,
                            environment_id=args.environment_id,
                            selected_source_tables=[result["table_name"]],
                            selected_target_tables=[result["table_name"]],
                        )
                    finally:
                        logging.disable(previous_logging_disable_level)
                rows_written = sum(item.rows_written for item in run_results)
                pipeline_status = "SUCCESS"
            except Exception as exc:
                execution_errors = True
                error_details = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "Governed full load failed for table %s.",
                    result["table_name"],
                )
                print(
                    f"Load failed for {result['table_name']}: "
                    f"{error_details}",
                    file=sys.stderr,
                )
            execution_summary.append(
                {
                    "table_name": result["table_name"],
                    "source_table": f"{args.source_schema}.{result['table_name']}",
                    "target_table": f"{args.target_schema}.{result['table_name']}",
                    "status": pipeline_status,
                    "rows_written": rows_written,
                    "mapping_status": result.get("mapping_status", "Unknown"),
                    "pipeline_status": result.get("pipeline_status", "Unknown"),
                    "error_details": error_details,
                }
            )

        if execution_summary:
            print("\nTABLE EXECUTION STATUS")
            summary_rows = [
                [
                    item["source_table"],
                    item["target_table"],
                    item["status"],
                    str(item["rows_written"]),
                    str(item["rows_written"]),
                    str(item["mapping_status"]),
                    str(item["pipeline_status"]),
                    item["error_details"],
                ]
                for item in execution_summary
            ]
            for line in _format_table(
                [
                    "Source Table",
                    "Target Table",
                    "Status",
                    "Source Rows Extracted",
                    "Target Rows Loaded",
                    "Mapping",
                    "Pipeline",
                    "Error Details",
                ],
                summary_rows,
            ):
                print(line)

            total_rows = sum(item["rows_written"] for item in execution_summary)
            successful_tables = sum(
                item["status"] == "SUCCESS" for item in execution_summary
            )
            print(
                "\nExecution Summary: "
                f"{successful_tables}/{len(execution_summary)} tables successful | "
                f"Total rows extracted: {total_rows} | Total rows loaded: {total_rows}"
            )
            if not execution_errors and successful_tables == len(execution_summary):
                print(
                    "Full load for all selected tables completed successfully."
                )
        return 1 if execution_errors or blocked else 0
    except Exception as exc:
        logger.exception("Unified full-load workflow failed.")
        print(
            f"Workflow failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
