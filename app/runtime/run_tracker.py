
"""Persistent pipeline and task execution tracking."""

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

import psycopg

from app.db.metastore import get_metastore_connection


class RuntimeRunTracker:
    """Persist pipeline and task execution status in the metastore."""

    def __init__(
        self,
        *,
        commit_transactions: bool = True,
        connection: psycopg.Connection | None = None,
    ) -> None:
        self._commit_transactions = commit_transactions
        self._connection = connection

    def _commit(self, conn: psycopg.Connection) -> None:
        if self._commit_transactions:
            conn.commit()

    def _connection_scope(self):
        """Use an injected connection or open a managed connection."""
        if self._connection is not None:
            from contextlib import nullcontext
            return nullcontext(self._connection)

        return get_metastore_connection()

    def start_pipeline(
        self,
        pipeline_version_id: int,
        tenant_id: int,
        environment_id: int,
    ) -> tuple[int, int, str]:
        if min(pipeline_version_id, tenant_id, environment_id) <= 0:
            raise ValueError(
                "Pipeline, tenant, and environment IDs must be positive."
            )

        batch_id = f"FULL_LOAD_{uuid4().hex}"

        with self._connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        pv.pipeline_id,
                        pv.tenant_id,
                        p.project_id
                    FROM orch.pipeline_version AS pv
                    JOIN orch.pipeline AS p
                      ON p.pipeline_id = pv.pipeline_id
                     AND p.tenant_id = pv.tenant_id
                    JOIN sec.project AS pr
                      ON pr.project_id = p.project_id
                     AND pr.tenant_id = p.tenant_id
                    JOIN sec.environment AS e
                      ON e.environment_id = %s
                     AND e.tenant_id = p.tenant_id
                    WHERE pv.pipeline_version_id = %s
                      AND pv.tenant_id = %s
                      AND p.status_code = 'ACTIVE'
                      AND pr.status_code = 'ACTIVE'
                      AND e.status_code = 'ACTIVE'
                    """,
                    (environment_id, pipeline_version_id, tenant_id),
                )
                metadata = cur.fetchone()

                if metadata is None:
                    raise LookupError(
                        "No active pipeline/project found for the supplied "
                        "pipeline version, tenant, and environment."
                    )

                _, resolved_tenant_id, project_id = metadata

                cur.execute(
                    """
                    INSERT INTO runtime.pipeline_run (
                        tenant_id,
                        project_id,
                        environment_id,
                        pipeline_version_id,
                        batch_id,
                        status_code,
                        trigger_type_code
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING run_id
                    """,
                    (
                        resolved_tenant_id,
                        project_id,
                        environment_id,
                        pipeline_version_id,
                        batch_id,
                        "RUNNING",
                        "MANUAL",
                    ),
                )
                run_id = cur.fetchone()[0]

            self._commit(conn)

        return run_id, project_id, batch_id

   
    def start_task(
        self,
        run_id: int,
        tenant_id: int,
        project_id: int,
        task_id: int,
        mapping_version_id: int | None,
        attempt_no: int = 1,
    ) -> tuple[int, datetime]:
        """Create a RUNNING task record and return its start timestamp."""

        if min(run_id, tenant_id, project_id, task_id, attempt_no) <= 0:
            raise ValueError(
                "Run, tenant, project, task, and attempt IDs must be positive."
            )

        with self._connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runtime.task_run (
                        run_id,
                        tenant_id,
                        project_id,
                        task_id,
                        mapping_version_id,
                        attempt_no,
                        status_code
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING task_run_id, started_at
                    """,
                    (
                        run_id,
                        tenant_id,
                        project_id,
                        task_id,
                        mapping_version_id,
                        attempt_no,
                        "RUNNING",
                    ),
                )
                task_run_id, started_at = cur.fetchone()

            self._commit(conn)

        return task_run_id, started_at


 
    def finish_task(
        self,
        task_run_id: int,
        started: datetime,
        status_code: str,
        rows_written: int = 0,
    ) -> None:
        """Finalize a task run using database-consistent timestamps."""

        if status_code not in {"SUCCESS", "FAILED"}:
            raise ValueError(
                "Task final status must be SUCCESS or FAILED."
            )

        if rows_written < 0:
            raise ValueError("rows_written cannot be negative.")

        with self._connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE runtime.task_run
                    SET status_code = %s,
                        rows_written = %s,
                        ended_at = GREATEST(
                            started_at,
                            CURRENT_TIMESTAMP
                        ),
                        duration_ms = GREATEST(
                            0,
                            (
                                EXTRACT(
                                    EPOCH FROM (
                                        GREATEST(
                                            started_at,
                                            CURRENT_TIMESTAMP
                                        ) - started_at
                                    )
                                ) * 1000
                            )::bigint
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE task_run_id = %s
                      AND status_code = 'RUNNING'
                    """,
                    (status_code, rows_written, task_run_id),
                )

                if cur.rowcount != 1:
                    raise LookupError(
                        f"Task run {task_run_id} was not found "
                        "in RUNNING status."
                    )

            self._commit(conn)

  
    def finish_pipeline(
        self,
        run_id: int,
        status_code: str,
    ) -> None:
        """Finalize a pipeline run using database-consistent timestamps."""

        if status_code not in {"SUCCESS", "FAILED"}:
            raise ValueError(
                "Pipeline final status must be SUCCESS or FAILED."
            )

        with self._connection_scope() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE runtime.pipeline_run
                    SET status_code = %s,
                        ended_at = GREATEST(
                            started_at,
                            CURRENT_TIMESTAMP
                        ),
                        duration_ms = GREATEST(
                            0,
                            (
                                EXTRACT(
                                    EPOCH FROM (
                                        GREATEST(
                                            started_at,
                                            CURRENT_TIMESTAMP
                                        ) - started_at
                                    )
                                ) * 1000
                            )::bigint
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE run_id = %s
                      AND status_code = 'RUNNING'
                    """,
                    (status_code, run_id),
                )

                if cur.rowcount != 1:
                    raise LookupError(
                        f"Pipeline run {run_id} was not found "
                        "in RUNNING status."
                    )

            self._commit(conn)
