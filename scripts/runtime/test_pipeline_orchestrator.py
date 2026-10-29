
from app.runtime.pipeline_orchestrator import PipelineOrchestrator


PIPELINE_VERSION_ID = 2
TENANT_ID = 1
ENVIRONMENT_ID = 1

# None means all configured tasks.
# Alternatively, provide the exact task_code values from metadata.
SELECTED_TASK_CODES = None


def main() -> None:
    orchestrator = PipelineOrchestrator()

    results = orchestrator.execute_pipeline(
        pipeline_version_id=PIPELINE_VERSION_ID,
        tenant_id=TENANT_ID,
        environment_id=ENVIRONMENT_ID,
        selected_task_codes=SELECTED_TASK_CODES,
    )

    print()
    print("TASK SUMMARY")
    print("-" * 80)

    for result in results:
        print(
            f"{result.task_code} | "
            f"Task ID: {result.task_id} | "
            f"Rows written: {result.rows_written}"
        )


if __name__ == "__main__":
    main()
