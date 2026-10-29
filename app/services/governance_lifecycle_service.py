"""Explicit governance lifecycle transitions for mapping and pipeline versions."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.db.metastore import get_metastore_connection


@dataclass(frozen=True)
class GovernanceTransitionResult:
    mapping_version_id: int
    mapping_status: str
    pipeline_version_id: int
    pipeline_status: str
    reason: str


class GovernanceLifecycleService:
    """Apply the repository governance lifecycle with development-only automation."""

    def __init__(self, connection_factory: Any = get_metastore_connection) -> None:
        self._connection_factory = connection_factory

    def activate_and_publish(
        self,
        *,
        tenant_id: int,
        project_id: int,
        environment_id: int,
        mapping_version_id: int,
        pipeline_version_id: int,
        auto_governance: bool | None = None,
    ) -> GovernanceTransitionResult:
        with self._connection_factory() as connection:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT e.is_production, e.environment_code, p.project_id
                        FROM sec.environment AS e
                        JOIN sec.project AS p ON p.project_id = %s
                        WHERE e.environment_id = %s
                          AND e.tenant_id = %s
                          AND p.tenant_id = %s
                        """,
                        (project_id, environment_id, tenant_id, tenant_id),
                    )
                    scope = cursor.fetchone()
                    if scope is None:
                        raise PermissionError(
                            "Governance scope is invalid: environment, tenant, project, or their relationships do not match."
                        )
                    is_production, environment_code, _ = scope

                    if auto_governance is None:
                        configured = os.getenv("UNIFIED_FULL_LOAD_AUTO_GOVERNANCE")
                        if configured is None:
                            auto_governance = not is_production
                        else:
                            auto_governance = configured.strip().lower() in {"1", "true", "yes", "on"}

                    if is_production and auto_governance:
                        raise PermissionError(
                            "Automatic governance approval is prohibited for a production environment."
                        )
                    if not auto_governance:
                        return self._read_statuses(cursor, tenant_id, mapping_version_id, pipeline_version_id)

                    cursor.execute(
                        "SELECT status_code FROM map.mapping_version WHERE mapping_version_id=%s AND tenant_id=%s",
                        (mapping_version_id, tenant_id),
                    )
                    mapping_status = str(cursor.fetchone()[0])
                    cursor.execute(
                        "SELECT status_code FROM orch.pipeline_version WHERE pipeline_version_id=%s AND tenant_id=%s",
                        (pipeline_version_id, tenant_id),
                    )
                    pipeline_status = str(cursor.fetchone()[0])
                    if mapping_status.upper() == "ACTIVE" and pipeline_status.upper() == "PUBLISHED":
                        connection.commit()
                        return GovernanceTransitionResult(
                            mapping_version_id,
                            mapping_status,
                            pipeline_version_id,
                            pipeline_status,
                            "Persisted governance statuses are already ACTIVE and PUBLISHED.",
                        )

                    principal_id = self._resolve_automation_principal(cursor, tenant_id)
                    self._validate_artifacts(cursor, tenant_id, project_id, mapping_version_id, pipeline_version_id)
                    self._activate_mapping(cursor, tenant_id, principal_id, mapping_version_id)
                    self._publish_pipeline(cursor, tenant_id, principal_id, pipeline_version_id)
                    self._record_release(
                        cursor,
                        tenant_id,
                        project_id,
                        principal_id,
                        mapping_version_id,
                        pipeline_version_id,
                    )

                    cursor.execute(
                        "SELECT status_code FROM map.mapping_version WHERE mapping_version_id = %s AND tenant_id = %s",
                        (mapping_version_id, tenant_id),
                    )
                    mapping_status = str(cursor.fetchone()[0])
                    cursor.execute(
                        "SELECT status_code FROM orch.pipeline_version WHERE pipeline_version_id = %s AND tenant_id = %s",
                        (pipeline_version_id, tenant_id),
                    )
                    pipeline_status = str(cursor.fetchone()[0])
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return GovernanceTransitionResult(
            mapping_version_id=mapping_version_id,
            mapping_status=mapping_status,
            pipeline_version_id=pipeline_version_id,
            pipeline_status=pipeline_status,
            reason=f"Automated development governance applied in {environment_code}.",
        )

    def _read_statuses(self, cursor: Any, tenant_id: int, mapping_id: int, pipeline_id: int) -> GovernanceTransitionResult:
        cursor.execute("SELECT status_code FROM map.mapping_version WHERE mapping_version_id=%s AND tenant_id=%s", (mapping_id, tenant_id))
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Mapping version {mapping_id} was not found for tenant {tenant_id}.")
        mapping_status = str(row[0])
        cursor.execute("SELECT status_code FROM orch.pipeline_version WHERE pipeline_version_id=%s AND tenant_id=%s", (pipeline_id, tenant_id))
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"Pipeline version {pipeline_id} was not found for tenant {tenant_id}.")
        pipeline_status = str(row[0])
        return GovernanceTransitionResult(mapping_id, mapping_status, pipeline_id, pipeline_status, "Existing governance statuses require manual approval/publication.")

    def _resolve_automation_principal(self, cursor: Any, tenant_id: int) -> int:
        cursor.execute(
            "SELECT principal_id FROM sec.principal WHERE tenant_id=%s AND status_code='ACTIVE' AND principal_type_code='SYSTEM' ORDER BY principal_id LIMIT 1",
            (tenant_id,),
        )
        row = cursor.fetchone()
        if row:
            return int(row[0])
        cursor.execute(
            """
            INSERT INTO sec.principal (
                tenant_id, principal_type_code, external_subject,
                login_name, display_name, status_code
            ) VALUES (%s, 'SYSTEM', 'unified-full-load-governance',
                      'unified-full-load-governance',
                      'Unified Full Load Governance', 'ACTIVE')
            RETURNING principal_id
            """,
            (tenant_id,),
        )
        return int(cursor.fetchone()[0])

    def _validate_artifacts(self, cursor: Any, tenant_id: int, project_id: int, mapping_id: int, pipeline_id: int) -> None:
        cursor.execute(
            """
            SELECT mv.mapping_id, m.project_id
            FROM map.mapping_version mv JOIN map.mapping m ON m.mapping_id=mv.mapping_id
            WHERE mv.mapping_version_id=%s AND mv.tenant_id=%s
            """,
            (mapping_id, tenant_id),
        )
        mapping = cursor.fetchone()
        if mapping is None or int(mapping[1]) != project_id:
            raise PermissionError("Mapping version or project scope is invalid.")
        cursor.execute(
            """
            SELECT pv.pipeline_id, p.project_id
            FROM orch.pipeline_version pv JOIN orch.pipeline p ON p.pipeline_id=pv.pipeline_id
            WHERE pv.pipeline_version_id=%s AND pv.tenant_id=%s
            """,
            (pipeline_id, tenant_id),
        )
        pipeline = cursor.fetchone()
        if pipeline is None or int(pipeline[1]) != project_id:
            raise PermissionError("Pipeline version or project scope is invalid.")
        cursor.execute(
            "SELECT 1 FROM orch.pipeline_task WHERE pipeline_version_id=%s AND tenant_id=%s AND mapping_version_id=%s",
            (pipeline_id, tenant_id, mapping_id),
        )
        if cursor.fetchone() is None:
            raise ValueError("Pipeline task does not reference the exact mapping version.")
        cursor.execute(
            "SELECT 1 FROM ingest.load_config WHERE mapping_version_id=%s AND is_active=TRUE AND truncate_before_load=TRUE",
            (mapping_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError("An active truncate-before-load configuration is missing.")

    @staticmethod
    def _activate_mapping(cursor: Any, tenant_id: int, principal_id: int, mapping_id: int) -> None:
        cursor.execute(
            """
            UPDATE map.mapping_version SET status_code='ACTIVE',
                approved_by_principal_id=%s, approved_at=COALESCE(approved_at, now()),
                published_by_principal_id=%s, published_at=COALESCE(published_at, now()),
                effective_from=COALESCE(effective_from, now()), updated_at=now()
            WHERE mapping_version_id=%s AND tenant_id=%s AND status_code IN ('DRAFT','ACTIVE')
            """,
            (principal_id, principal_id, mapping_id, tenant_id),
        )

    @staticmethod
    def _publish_pipeline(cursor: Any, tenant_id: int, principal_id: int, pipeline_id: int) -> None:
        cursor.execute(
            "SELECT status_code FROM map.mapping_version mv JOIN orch.pipeline_task pt ON pt.mapping_version_id=mv.mapping_version_id WHERE pt.pipeline_version_id=%s AND mv.tenant_id=%s",
            (pipeline_id, tenant_id),
        )
        statuses = [str(row[0]).upper() for row in cursor.fetchall()]
        if statuses and any(status != "ACTIVE" for status in statuses):
            raise PermissionError("Pipeline publication is blocked by an inactive mapping version.")
        cursor.execute(
            """
            UPDATE orch.pipeline_version SET status_code='PUBLISHED',
                approved_by_principal_id=%s, approved_at=COALESCE(approved_at, now()),
                published_by_principal_id=%s, published_at=COALESCE(published_at, now()),
                effective_from=COALESCE(effective_from, now()), updated_at=now()
            WHERE pipeline_version_id=%s AND tenant_id=%s AND status_code IN ('DRAFT','PUBLISHED')
            """,
            (principal_id, principal_id, pipeline_id, tenant_id),
        )

    @staticmethod
    def _record_release(cursor: Any, tenant_id: int, project_id: int, principal_id: int, mapping_id: int, pipeline_id: int) -> None:
        cursor.execute("SELECT config_hash FROM map.mapping_version WHERE mapping_version_id=%s", (mapping_id,))
        mapping_hash = str(cursor.fetchone()[0])
        cursor.execute("SELECT config_hash FROM orch.pipeline_version WHERE pipeline_version_id=%s", (pipeline_id,))
        pipeline_hash = str(cursor.fetchone()[0])
        release_hash = mapping_hash + pipeline_hash
        cursor.execute(
            """
            INSERT INTO gov.change_request (
                tenant_id, project_id, change_type_code,
                requested_by_principal_id, status_code, reason,
                created_by_principal_id, updated_by_principal_id
            ) VALUES (%s,%s,'DATA_FULL_LOAD',%s,'APPROVED',
                      'Automated development governance for unified full load',%s,%s)
            RETURNING change_id
            """,
            (tenant_id, project_id, principal_id, principal_id, principal_id),
        )
        change_id = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO gov.release (
                tenant_id, project_id, release_version, status_code,
                config_manifest_hash, approved_by_principal_id, approved_at,
                published_at, created_by_principal_id, updated_by_principal_id
            ) VALUES (%s,%s,%s,'PUBLISHED',%s,%s,now(),now(),%s,%s)
            RETURNING release_id
            """,
            (tenant_id, project_id, f"FULL_LOAD-{mapping_id}-{pipeline_id}", release_hash,
             principal_id, principal_id, principal_id),
        )
        release_id = int(cursor.fetchone()[0])
        cursor.execute(
            "UPDATE gov.change_request SET target_release_id=%s WHERE change_id=%s",
            (release_id, change_id),
        )
        cursor.execute(
            "INSERT INTO gov.release_item (tenant_id,release_id,item_type_code,mapping_version_id,item_hash,sequence_no) VALUES (%s,%s,'MAPPING_VERSION',%s,%s,1)",
            (tenant_id, release_id, mapping_id, mapping_hash),
        )
        cursor.execute(
            "INSERT INTO gov.release_item (tenant_id,release_id,item_type_code,pipeline_version_id,item_hash,sequence_no) VALUES (%s,%s,'PIPELINE_VERSION',%s,%s,2)",
            (tenant_id, release_id, pipeline_id, pipeline_hash),
        )
        cursor.execute(
            "INSERT INTO gov.approval (tenant_id,change_id,approver_principal_id,decision_code,comments,created_by_principal_id,updated_by_principal_id) VALUES (%s,%s,%s,'APPROVED','Automated development approval',%s,%s)",
            (tenant_id, change_id, principal_id, principal_id, principal_id),
        )
        cursor.execute(
            "INSERT INTO gov.approval (tenant_id,release_id,approver_principal_id,decision_code,comments,created_by_principal_id,updated_by_principal_id) VALUES (%s,%s,%s,'APPROVED','Automated development publication',%s,%s)",
            (tenant_id, release_id, principal_id, principal_id, principal_id),
        )
