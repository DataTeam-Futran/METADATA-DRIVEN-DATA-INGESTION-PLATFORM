
"""Verify tracker lifecycle using a transaction that is rolled back."""

from app.db.metastore import get_metastore_connection
from app.runtime.run_tracker import RuntimeRunTracker


PIPELINE_VERSION_ID = 2
TENANT_ID = 1
ENVIRONMENT_ID = 1

# Use the existing Customer task and mapping metadata.
TASK_ID = 2
MAPPING_VERSION_ID = 2


def main() -> None:
    with get_metastore_connection() as conn:
        tracker = RuntimeRunTracker(
            connection=conn,
            commit_transactions=False,
        )

        run_id = None

        try:
            run_id, project_id, batch_id = tracker.start_pipeline(
                pipeline_version_id=PIPELINE_VERSION_ID,
                tenant_id=TENANT_ID,
                environment_id=ENVIRONMENT_ID,
            )

            task_run_id, started = tracker.start_task(
                run_id=run_id,
                tenant_id=TENANT_ID,
                project_id=project_id,
                task_id=TASK_ID,
                mapping_version_id=MAPPING_VERSION_ID,
            )

            tracker.finish_task(
                task_run_id=task_run_id,
                started=started,
                status_code="FAILED",
                rows_written=0,
            )

            tracker.finish_pipeline(
                run_id=run_id,
                status_code="FAILED",
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT status_code
                    FROM runtime.pipeline_run
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                pipeline_status = cur.fetchone()[0]

                cur.execute(
                    """
                    SELECT status_code, rows_written
                    FROM runtime.task_run
                    WHERE task_run_id = %s
                    """,
                    (task_run_id,),
                )
                task_status = cur.fetchone()

            assert pipeline_status == "FAILED", pipeline_status
            assert task_status == ("FAILED", 0), task_status

            print("Pipeline tracking lifecycle: PASSED")
            print("Task tracking lifecycle    : PASSED")
            print("Transaction rollback       : PENDING")

        finally:
            conn.rollback()

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM runtime.pipeline_run
                WHERE run_id = %s
                """,
                (run_id,),
            )
            remaining = cur.fetchone()[0]

        assert remaining == 0, (
            "Rollback failed: the test pipeline record still exists."
        )

        print("Transaction rollback       : PASSED")
        print("No test pipeline record remains.")


if __name__ == "__main__":
    main()
