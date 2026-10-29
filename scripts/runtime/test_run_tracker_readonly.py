
"""Read-only verification of existing runtime tracking records."""

from app.db.metastore import get_metastore_connection


def main() -> None:
    with get_metastore_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    run_id,
                    tenant_id,
                    project_id,
                    environment_id,
                    pipeline_version_id,
                    batch_id,
                    status_code,
                    trigger_type_code,
                    started_at,
                    ended_at,
                    duration_ms
                FROM runtime.pipeline_run
                WHERE tenant_id = %s
                  AND pipeline_version_id = %s
                ORDER BY run_id DESC
                LIMIT 10
                """,
                (1, 2),
            )

            print("Recent Customer pipeline runs:")
            rows = cur.fetchall()

            if not rows:
                print("No existing runs found.")
            else:
                for row in rows:
                    print(row)

            cur.execute(
                """
                SELECT
                    task_run_id,
                    run_id,
                    task_id,
                    mapping_version_id,
                    attempt_no,
                    status_code,
                    rows_written,
                    started_at,
                    ended_at,
                    duration_ms
                FROM runtime.task_run
                WHERE tenant_id = %s
                ORDER BY task_run_id DESC
                LIMIT 10
                """,
                (1,),
            )

            print("\nRecent task runs:")
            task_rows = cur.fetchall()

            if not task_rows:
                print("No existing task runs found.")
            else:
                for row in task_rows:
                    print(row)


if __name__ == "__main__":
    main()
