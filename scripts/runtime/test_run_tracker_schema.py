
"""Read-only checks for runtime tracking prerequisites."""

from app.db.metastore import get_metastore_connection


def main() -> None:
    with get_metastore_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    e.environment_id,
                    e.tenant_id,
                    e.status_code
                FROM sec.environment AS e
                WHERE e.environment_id IN (1, 3)
                ORDER BY e.environment_id
                """
            )
            print("Environment metadata:")
            for row in cur.fetchall():
                print(row)

            cur.execute(
                """
                SELECT
                    table_name,
                    column_name,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'runtime'
                  AND table_name IN ('pipeline_run', 'task_run')
                  AND column_name IN (
                      'run_id',
                      'tenant_id',
                      'project_id',
                      'environment_id',
                      'pipeline_version_id',
                      'batch_id',
                      'status_code',
                      'trigger_type_code',
                      'task_run_id',
                      'task_id',
                      'mapping_version_id',
                      'attempt_no',
                      'rows_written',
                      'ended_at',
                      'duration_ms',
                      'updated_at'
                  )
                ORDER BY table_name, ordinal_position
                """
            )
            print("\nRuntime tracking columns:")
            for row in cur.fetchall():
                print(row)


if __name__ == "__main__":
    main()
