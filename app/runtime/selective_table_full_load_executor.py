"""CLI for full-loading selected tables discovered in a source schema."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.runtime.multi_table_full_load_executor import (
    MultiTableFullLoadExecutor,
    MultiTableLoadSummary,
)

def parse_table_selection(
    selection: str,
    discovered_tables: list[str],
) -> list[str]:
    """Parse comma-separated table names or 1-based discovery-list indexes."""
    requested = [name.strip() for name in selection.split(",") if name.strip()]
    if not requested:
        raise ValueError("Enter at least one source table name.")

    selected_tables: list[str] = []
    unknown_tables: list[str] = []
    for name in requested:
        if name in discovered_tables:
            selected_tables.append(name)
        elif name.isdecimal() and 1 <= int(name) <= len(discovered_tables):
            selected_tables.append(discovered_tables[int(name) - 1])
        else:
            unknown_tables.append(name)
    if unknown_tables:
        raise ValueError(
            "Tables not found in the source schema: "
            + ", ".join(unknown_tables)
        )
    return list(dict.fromkeys(selected_tables))


def render_discovery_report(
    source_schema: str,
    discovered_tables: list[str],
) -> str:
    """Render all discovered source tables before the user selects any."""
    discovery_rows = [
        [str(index), source_schema, table_name]
        for index, table_name in enumerate(discovered_tables, start=1)
    ] or [["-", source_schema, "No base tables found"]]
    lines = [
        f"SOURCE TABLE DISCOVERY ({len(discovered_tables)} tables)",
        *_format_table(
            ["#", "Source Schema", "Discovered Table"],
            discovery_rows,
        ),
    ]
    return "\n".join(lines)


def render_selected_tables(selected_tables: list[str]) -> str:
    """Render the chosen source tables before starting the load."""
    selected_rows = [
        [str(index), table_name]
        for index, table_name in enumerate(selected_tables, start=1)
    ] or [["-", "No tables selected"]]
    return "\n".join(
        [
            f"TABLES SELECTED FOR LOAD ({len(selected_tables)})",
            *_format_table(["#", "Selected Source Table"], selected_rows),
        ]
    )


def render_selective_report(
    summary: MultiTableLoadSummary,
) -> str:
    """Render only successfully loaded target tables and final totals."""
    status_rows = [
        [
            result.table_name,
            result.status,
            str(result.source_record_count or 0),
            str(result.target_record_count or 0),
            str(result.rows_extracted),
            str(result.rows_loaded),
            result.start_time,
            result.end_time,
            result.error_details or "",
        ]
        for result in summary.tables
    ] or [["-", "N/A", "0", "0", "0", "0", "-", "-", ""]]
    lines = ["TABLE EXECUTION STATUS"]
    lines.extend(
        _format_table(
            [
                "Table",
                "Status",
                "Source Rows",
                "Target Rows",
                "Rows Extracted",
                "Rows Loaded",
                "Started",
                "Finished",
                "Error Details",
            ],
            status_rows,
        )
    )
    loaded_rows = [
        [str(index), summary.target_schema, result.table_name]
        for index, result in enumerate(
            (result for result in summary.tables if result.status == "Success"),
            start=1,
        )
    ] or [["-", summary.target_schema, "No tables loaded"]]
    loaded_count = sum(result.status == "Success" for result in summary.tables)
    lines.extend(["", f"TARGET TABLES LOADED ({loaded_count})"])
    lines.extend(
        _format_table(
            ["#", "Target Schema", "Loaded Table"],
            loaded_rows,
        )
    )

    lines.extend(["", "EXECUTION SUMMARY"])
    lines.extend(
        _format_table(
            ["Metric", "Value"],
            [
                ["Source schema", summary.source_schema],
                ["Target schema", summary.target_schema],
                ["Source tables discovered", str(summary.discovered_table_count)],
                ["Tables selected", str(len(summary.tables))],
                ["Tables loaded successfully", str(summary.succeeded)],
                ["Tables failed", str(summary.failed)],
                ["Total rows extracted", str(summary.total_rows_extracted)],
                ["Total rows loaded", str(summary.total_rows_loaded)],
                ["Started", summary.start_time],
                ["Finished", summary.end_time or "In progress"],
            ],
        )
    )
    return "\n".join(lines)


def _format_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a plain-text table without third-party dependencies."""
    normalized_rows = [
        [str(value).replace("\r", " ").replace("\n", " ") for value in row]
        for row in rows
    ]
    widths = [
        max(
            len(headers[index]),
            *(len(row[index]) for row in normalized_rows),
        )
        for index in range(len(headers))
    ]

    def format_row(row: list[str]) -> str:
        return "| " + " | ".join(
            value.ljust(widths[index])
            for index, value in enumerate(row)
        ) + " |"

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
    return [
        separator,
        format_row(headers),
        separator,
        *(format_row(row) for row in normalized_rows),
        separator,
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Discover source tables and full-load only selected tables using "
            "the truncate-and-insert strategy."
        )
    )
    parser.add_argument("--source-schema", default="public")
    parser.add_argument("--target-schema", default="warehouse")
    parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TABLE",
        help=(
            "Skip the interactive selection and load one or more exact source "
            "table names or 1-based discovery-list numbers."
        ),
    )
    parser.add_argument("--source-connection-id", type=int, default=1)
    parser.add_argument("--target-connection-id", type=int, default=11)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the execution summary as JSON instead of a text report.",
    )
    arguments = parser.parse_args()

    source_schema = arguments.source_schema
    target_schema = arguments.target_schema

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    executor = MultiTableFullLoadExecutor(
        source_connection_id=arguments.source_connection_id,
        target_connection_id=arguments.target_connection_id,
        batch_size=arguments.batch_size,
    )
    try:
        discovered_tables = executor.discover_source_tables(source_schema)
    except Exception as exc:
        parser.error(f"Unable to discover source tables: {exc}")

    print()
    print(render_discovery_report(source_schema, discovered_tables))
    if not discovered_tables:
        parser.error(
            f"No base tables found in source schema {source_schema!r}."
        )

    if arguments.tables is None:
        while True:
            try:
                selection = input(
                    "\nChoose table numbers or names, separated by commas "
                    "(the load will not start until the selection is valid): "
                )
                selected_tables = parse_table_selection(
                    selection,
                    discovered_tables,
                )
                break
            except ValueError as exc:
                print(f"Invalid selection: {exc}")
            except EOFError:
                parser.error("Table selection was not provided.")
    else:
        try:
            selected_tables = parse_table_selection(
                ",".join(arguments.tables),
                discovered_tables,
            )
        except ValueError as exc:
            parser.error(str(exc))

    print()
    print(render_selected_tables(selected_tables))

    try:
        summary = executor.execute(
            source_schema=source_schema,
            target_schema=target_schema,
            table_names=selected_tables,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if arguments.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print()
        print(render_selective_report(summary))
    if summary.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
