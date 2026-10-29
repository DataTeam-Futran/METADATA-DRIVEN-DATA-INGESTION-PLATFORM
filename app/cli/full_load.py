
"""CLI for metadata-driven full-load pipeline execution."""

import argparse
import sys

from app.runtime.pipeline_orchestrator import PipelineOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute a metadata-driven full-load pipeline "
            "for all configured tasks or a selected subset."
        )
    )

    parser.add_argument(
        "--pipeline-version-id",
        type=int,
        required=True,
        help="Pipeline version ID from metadata.",
    )
    parser.add_argument(
        "--tenant-id",
        type=int,
        required=True,
        help="Tenant ID.",
    )
    parser.add_argument(
        "--environment-id",
        type=int,
        required=True,
        help="Environment ID.",
    )
    parser.add_argument(
        "--task-code",
        action="append",
        dest="task_codes",
        help="Task code to execute. Repeat to select multiple tasks.",
    )
    parser.add_argument(
        "--source-table",
        action="append",
        dest="source_tables",
        help="Source table name, schema.table, or catalog.schema.table.",
    )
    parser.add_argument(
        "--target-table",
        action="append",
        dest="target_tables",
        help="Target table name, schema.table, or catalog.schema.table.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Explicitly authorize full-load execution. "
            "Without this flag, no pipeline is executed."
        ),
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.execute:
        parser.error(
            "Execution was not authorized. Add --execute only after "
            "confirming the selected pipeline and target tables."
        )

    if args.pipeline_version_id <= 0:
        parser.error("--pipeline-version-id must be greater than zero.")

    if args.tenant_id <= 0:
        parser.error("--tenant-id must be greater than zero.")

    if args.environment_id <= 0:
        parser.error("--environment-id must be greater than zero.")

    print("=" * 80)
    print("METADATA-DRIVEN FULL-LOAD CLI")
    print("=" * 80)
    print(f"Pipeline version : {args.pipeline_version_id}")
    print(f"Tenant           : {args.tenant_id}")
    print(f"Environment      : {args.environment_id}")
    print(f"Task filters     : {args.task_codes or 'All configured tasks'}")
    print(f"Source filters   : {args.source_tables or 'All configured sources'}")
    print(f"Target filters   : {args.target_tables or 'All configured targets'}")
    print()

    try:
        orchestrator = PipelineOrchestrator()

        results = orchestrator.execute_pipeline(
            pipeline_version_id=args.pipeline_version_id,
            tenant_id=args.tenant_id,
            environment_id=args.environment_id,
            selected_task_codes=args.task_codes,
            selected_source_tables=args.source_tables,
            selected_target_tables=args.target_tables,
        )

        print()
        print("=" * 80)
        print("CLI EXECUTION SUMMARY")
        print("=" * 80)

        total_rows_written = 0

        for result in results:
            total_rows_written += result.rows_written
            print(
                f"Task ID={result.task_id} | "
                f"Code={result.task_code} | "
                f"Rows written={result.rows_written}"
            )

        print(f"Successful tasks   : {len(results)}")
        print(f"Total rows written : {total_rows_written}")
        print("CLI result         : SUCCESS")

        return 0

    except Exception as exc:
        print()
        print("CLI result : FAILED", file=sys.stderr)
        print(f"Reason     : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
