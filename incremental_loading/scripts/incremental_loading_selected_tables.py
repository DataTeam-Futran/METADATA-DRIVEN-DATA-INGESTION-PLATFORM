"""Select source tables and incrementally append only those tables."""

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

if __package__:
    from . import incremental_loading_multiple_tables as multi_table_loader
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from incremental_loading.scripts import (
        incremental_loading_multiple_tables as multi_table_loader,
    )

from app.runtime.connection_resolver import RuntimeConnectionResolver


def select_named_tables(
    requested_tables: Sequence[str],
    available_tables: Sequence[str],
) -> list[str]:
    """Validate exact table names requested through the command line."""
    if not requested_tables:
        raise ValueError("Select at least one source table.")

    duplicates = sorted(
        {
            table_name
            for table_name in requested_tables
            if requested_tables.count(table_name) > 1
        }
    )
    if duplicates:
        raise ValueError(
            "Duplicate table selections: " + ", ".join(duplicates)
        )

    available = set(available_tables)
    unknown_tables = [
        table_name for table_name in requested_tables if table_name not in available
    ]
    if unknown_tables:
        raise ValueError(
            "Tables not found in the source schema: "
            + ", ".join(unknown_tables)
        )
    return list(requested_tables)


def select_table_numbers(
    selection: str,
    available_tables: Sequence[str],
) -> list[str]:
    """Resolve comma-separated 1-based menu choices to source table names."""
    tokens = [token.strip() for token in selection.split(",")]
    if not tokens or any(not token for token in tokens):
        raise ValueError("Enter one or more table numbers separated by commas.")

    indexes: list[int] = []
    for token in tokens:
        if not token.isdecimal():
            raise ValueError(f"{token!r} is not a valid table number.")
        index = int(token)
        if index < 1 or index > len(available_tables):
            raise ValueError(
                f"Table number {index} is outside the valid range "
                f"1-{len(available_tables)}."
            )
        if index in indexes:
            raise ValueError(f"Table number {index} was selected more than once.")
        indexes.append(index)
    return [available_tables[index - 1] for index in indexes]


def print_table_choices(source_tables: Sequence[str]) -> None:
    """Display the discovered source-table count and numbered choices."""
    print(f"Source tables discovered: {len(source_tables)}")
    for index, table_name in enumerate(source_tables, start=1):
        print(f"  {index}. {table_name}")


def prompt_for_tables(source_tables: Sequence[str]) -> list[str]:
    """Prompt until valid menu choices are provided, or the user cancels."""
    while True:
        selection = input(
            "Select table number(s) separated by commas, or q to cancel: "
        ).strip()
        if selection.lower() == "q":
            return []
        try:
            return select_table_numbers(selection, source_tables)
        except ValueError as error:
            print(f"Invalid selection: {error}")


def main(argv: Sequence[str] | None = None) -> int:
    """Discover source tables, select a subset, and append only that subset."""
    parser = argparse.ArgumentParser(
        description=(
            "Discover source tables and incrementally append only selected tables."
        )
    )
    parser.add_argument(
        "--list-tables",
        action="store_true",
        help="list source tables and exit without loading data",
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        metavar="TABLE",
        help="exact source table names to load; select one or more",
    )
    args = parser.parse_args(argv)

    resolver = RuntimeConnectionResolver()
    source_connector = resolver.resolve(multi_table_loader.SOURCE_CONNECTION_ID)
    source_connector.connect()
    try:
        source_tables = source_connector.list_tables(multi_table_loader.SOURCE_SCHEMA)
        source_database = source_connector.metadata.database_name
    finally:
        source_connector.close()

    if not source_tables:
        print(
            "No source tables found in "
            f"{multi_table_loader.SOURCE_SCHEMA!r}."
        )
        return 1

    print_table_choices(source_tables)
    if args.list_tables:
        return 0

    if args.tables:
        try:
            selected_tables = select_named_tables(args.tables, source_tables)
        except ValueError as error:
            parser.error(str(error))
    else:
        selected_tables = prompt_for_tables(source_tables)
        if not selected_tables:
            print("Selection cancelled; no tables were loaded.")
            return 0

    target_connector = resolver.resolve(
        multi_table_loader.TARGET_CONNECTION_ID,
        database_name_override=multi_table_loader.TARGET_DATABASE,
    )
    print("=" * 72)
    print("SELECTED-TABLE INCREMENTAL APPEND")
    print(
        f"Source: {source_database}.{multi_table_loader.SOURCE_SCHEMA}"
    )
    print(
        f"Target: {multi_table_loader.TARGET_DATABASE}."
        f"{multi_table_loader.TARGET_SCHEMA}"
    )
    print(f"Tables selected: {len(selected_tables)}")
    print("Only the selected tables will be loaded.")
    print("=" * 72)

    loaded_tables: list[str] = []
    rows_appended = 0
    failures: list[tuple[str, str]] = []
    for table_name in selected_tables:
        try:
            _, table_rows_appended, _ = multi_table_loader.run_table(
                source_connector,
                target_connector,
                table_name,
                display_columns_and_data=False,
            )
            loaded_tables.append(table_name)
            rows_appended += table_rows_appended
        except Exception as error:
            failures.append((table_name, str(error)))
            print(f"\nFAILED TABLE: {table_name}: {error}")

    multi_table_loader.print_details_section(
        "SELECTED-TABLE TOTALS",
        [
            ("Tables discovered in source", len(source_tables)),
            ("Tables selected for incremental loading", len(selected_tables)),
            (
                f"Tables loaded successfully into target ({len(loaded_tables)})",
                ", ".join(loaded_tables) or "None",
            ),
            ("Rows appended to target tables", rows_appended),
        ],
    )
    if failures:
        print(
            "One or more selected tables failed: "
            + "; ".join(f"{table}: {error}" for table, error in failures)
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
