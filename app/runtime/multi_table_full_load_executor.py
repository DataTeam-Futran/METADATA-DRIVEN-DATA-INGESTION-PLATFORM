"""Metadata-driven, schema-wide truncate-and-insert full loads."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    project_root = str(Path(__file__).resolve().parents[2])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.connectors.base import BaseConnector
from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.schema_comparison import (
    SchemaCompatibility,
    assess_column_compatibility,
)

logger = logging.getLogger(__name__)


@dataclass
class TableLoadResult:
    """Capture one table's mapping, load metrics, validation, and failure details.

    ``column_mappings`` records the current same-name mapping policy: each
    discovered source column is written to a target column with the same name.
    """

    table_name: str
    start_time: str
    column_mappings: list[dict[str, str]] = field(default_factory=list)
    end_time: str = ""
    rows_extracted: int = 0
    rows_loaded: int = 0
    source_record_count: int | None = None
    target_record_count: int | None = None
    schema_validation_status: str = "Not checked"
    load_compatibility_status: str = "Not checked"
    schema_differences: list[str] = field(default_factory=list)
    compatible_schema_differences: list[str] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    status: str = "Failed"
    error_details: str | None = None


@dataclass
class MultiTableLoadSummary:
    """Aggregate connection, schema, discovery, and load results for one run.

    The source and target schemas are kept separately because the loader
    transfers each table from ``source_schema`` into ``target_schema``; the
    table name itself is preserved unless a future mapping policy says
    otherwise.
    """

    source_database: str | None
    target_database: str | None
    source_connection_name: str
    target_connection_name: str
    source_schema: str
    target_schema: str
    source_connection_id: int
    target_connection_id: int
    start_time: str
    end_time: str = ""
    discovered_source_tables: list[str] = field(default_factory=list)
    tables: list[TableLoadResult] = field(default_factory=list)

    @property
    def succeeded(self) -> int:
        """Count tables whose loads and row-count validations both succeeded."""
        return sum(table.status == "Success" for table in self.tables)

    @property
    def failed(self) -> int:
        """Count tables that failed to load or failed validation."""
        return sum(table.status == "Failed" for table in self.tables)

    @property
    def total_rows_extracted(self) -> int:
        """Return the sum of source rows read across processed tables."""
        return sum(table.rows_extracted for table in self.tables)

    @property
    def total_rows_loaded(self) -> int:
        """Return the sum of rows written to the target across tables."""
        return sum(table.rows_loaded for table in self.tables)

    @property
    def discovered_table_count(self) -> int:
        """Return the source discovery count, including unselected tables."""
        return len(self.discovered_source_tables or self.tables)

    def render_report(self) -> str:
        """Render connection details, schema/table mapping, and run results.

        The source-to-target mapping shown here pairs the same table name
        across the separately configured source and target schemas.
        """
        lines = ["ALL-TABLE FULL LOAD REPORT", "", "CONNECTIONS"]
        lines.extend(
            self._format_table(
                ["Role", "Database", "Schema", "Connection"],
                [
                    [
                        "Source",
                        self.source_database or "Unknown",
                        self.source_schema,
                        self.source_connection_name,
                    ],
                    [
                        "Target",
                        self.target_database or "Unknown",
                        self.target_schema,
                        self.target_connection_name,
                    ],
                ],
            )
        )
        lines.extend(
            [
                "",
                f"SOURCE TABLE DISCOVERY ({self.discovered_table_count} tables)",
            ]
        )
        discovered_tables = self.discovered_source_tables or [
            result.table_name for result in self.tables
        ]
        discovery_rows = [
            [str(index), self.source_schema, table_name]
            for index, table_name in enumerate(discovered_tables, start=1)
        ]
        if not discovery_rows:
            discovery_rows = [["-", self.source_schema, "No base tables found"]]
        lines.extend(
            self._format_table(
                ["#", "Source Schema", "Discovered Table"],
                discovery_rows,
            )
        )
        loaded_tables = [
            table for table in self.tables if table.status == "Success"
        ]
        target_rows = [
            [str(index), self.target_schema, table.table_name]
            for index, table in enumerate(loaded_tables, start=1)
        ]
        if not target_rows:
            target_rows = [["-", self.target_schema, "No tables loaded"]]
        lines.extend(
            [
                "",
                f"TARGET TABLES LOADED ({len(loaded_tables)} tables)",
            ]
        )
        lines.extend(
            self._format_table(
                ["#", "Target Schema", "Loaded Table"],
                target_rows,
            )
        )
        status_rows = [
            [
                f"{self.source_schema}.{table.table_name}",
                f"{self.target_schema}.{table.table_name}",
                table.status,
                (
                    f"{table.source_record_count or 0}/"
                    f"{table.target_record_count or 0}"
                ),
                str(table.rows_extracted),
                str(table.rows_loaded),
                table.schema_validation_status,
                table.load_compatibility_status,
            ]
            for table in self.tables
        ] or [
            [
                "-",
                "-",
                "N/A",
                "0",
                "0",
                "0",
                "Not checked",
                "Not checked",
            ]
        ]
        lines.extend(["", "TABLE EXECUTION STATUS"])
        lines.extend(
            self._format_table(
                [
                    "Source Table",
                    "Target Table",
                    "Status",
                    "Rows S/T",
                    "Read",
                    "Written",
                    "Schema Match",
                    "Load",
                ],
                status_rows,
                max_widths=[20, 20, 8, 9, 7, 8, 12, 10],
            )
        )
        detail_rows: list[list[str]] = []
        for table in self.tables:
            table_name = f"{self.source_schema}.{table.table_name}"
            table_details = [
                ("Started", table.start_time),
                ("Finished", table.end_time),
                (
                    "Schema differences",
                    "; ".join(table.schema_differences) or "None",
                ),
                (
                    "Load-compatible differences",
                    "; ".join(table.compatible_schema_differences) or "None",
                ),
                ("Error", table.error_details or "None"),
            ]
            detail_rows.extend(
                [[table_name, label, value] for label, value in table_details]
            )
        if detail_rows:
            lines.extend(["", "TABLE EXECUTION DETAILS"])
            lines.extend(
                self._format_table(
                    ["Source Table", "Detail", "Information"],
                    detail_rows,
                    max_widths=[22, 24, 68],
                )
            )
        lines.extend(["", "EXECUTION SUMMARY"])
        lines.extend(
            self._format_table(
                ["Metric", "Value"],
                [
                    ["Tables discovered", str(self.discovered_table_count)],
                    ["Tables loaded successfully", str(self.succeeded)],
                    ["Tables failed", str(self.failed)],
                    ["Total rows extracted", str(self.total_rows_extracted)],
                    ["Total rows loaded", str(self.total_rows_loaded)],
                    ["Started", self.start_time],
                    ["Finished", self.end_time or "In progress"],
                ],
            )
        )
        return "\n".join(lines)

    @staticmethod
    def _format_table(
        headers: list[str],
        rows: list[list[str]],
        max_widths: list[int] | None = None,
    ) -> list[str]:
        """Format aligned tables, wrapping long cell values when requested."""
        if max_widths is not None and len(max_widths) != len(headers):
            raise ValueError("max_widths must have one entry per table column.")

        widths = []
        for index, header in enumerate(headers):
            content_width = max(
                (len(str(row[index])) for row in rows),
                default=0,
            )
            if max_widths is None:
                widths.append(max(len(header), content_width))
            else:
                widths.append(
                    min(
                        max(len(header), content_width),
                        max_widths[index],
                    )
                )

        def wrap_value(value: str, width: int) -> list[str]:
            paragraphs = str(value).replace("\r", "").split("\n")
            wrapped = [
                part
                for paragraph in paragraphs
                for part in (
                    textwrap.wrap(
                        paragraph,
                        width=width,
                        replace_whitespace=True,
                        break_long_words=True,
                        break_on_hyphens=False,
                    )
                    or [""]
                )
            ]
            return wrapped or [""]

        normalized_rows = [
            [
                wrap_value(str(value), widths[index])
                for index, value in enumerate(row)
            ]
            for row in rows
        ]

        def format_row(row: list[str]) -> str:
            return "| " + " | ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            ) + " |"

        separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"
        formatted_rows: list[str] = []
        for row in normalized_rows:
            row_height = max(len(cell) for cell in row)
            for line_index in range(row_height):
                formatted_rows.append(
                    format_row(
                        [
                            cell[line_index] if line_index < len(cell) else ""
                            for cell in row
                        ]
                    )
                )
        return [
            separator,
            format_row(headers),
            separator,
            *formatted_rows,
            separator,
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the run summary and per-table details for JSON output."""
        return {
            "source_database": self.source_database,
            "target_database": self.target_database,
            "source_connection_name": self.source_connection_name,
            "target_connection_name": self.target_connection_name,
            "source_schema": self.source_schema,
            "target_schema": self.target_schema,
            "source_connection_id": self.source_connection_id,
            "target_connection_id": self.target_connection_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "tables_discovered": self.discovered_table_count,
            "tables_processed": len(self.tables),
            "discovered_source_tables": self.discovered_source_tables,
            "tables_succeeded": self.succeeded,
            "tables_failed": self.failed,
            "total_rows_extracted": self.total_rows_extracted,
            "total_rows_loaded": self.total_rows_loaded,
            "tables": [asdict(table) for table in self.tables],
        }


@dataclass
class TableSchemaPreparation:
    """Report one table's target schema preparation without loading data."""

    table_name: str
    target_was_created: bool = False
    source_columns: list[dict[str, Any]] = field(default_factory=list)
    target_columns: list[dict[str, Any]] = field(default_factory=list)
    schema_validation_status: str = "Not checked"
    load_compatibility_status: str = "Not checked"
    error_details: str | None = None


class MultiTableFullLoadExecutor:
    """Discover source tables and load their same-named target tables.

    Source and target connection identifiers are resolved at runtime, keeping
    credentials out of the loader. The configured schemas may differ; table
    and column names are mapped identically by default.
    """

    def __init__(
        self,
        connection_resolver: RuntimeConnectionResolver | None = None,
        source_connection_id: int = 1,
        target_connection_id: int = 11,
        batch_size: int = 1000,
    ) -> None:
        """Configure runtime connections and the maximum rows read per batch."""
        if source_connection_id <= 0 or target_connection_id <= 0:
            raise ValueError("Connection IDs must be greater than zero.")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")

        self._connection_resolver = (
            connection_resolver
            if connection_resolver is not None
            else RuntimeConnectionResolver()
        )
        self.source_connection_id = source_connection_id
        self.target_connection_id = target_connection_id
        self.batch_size = batch_size

    def discover_source_tables(self, source_schema: str) -> list[str]:
        """List base tables in the source schema without changing the target.

        ``source_schema`` identifies where discovery runs; target schema
        resolution is not needed until execution begins.
        """
        self._validate_schema_name(source_schema, "source_schema")
        source_connector = self._connection_resolver.resolve(
            self.source_connection_id
        )
        connect_attempted = False
        try:
            connect_attempted = True
            source_connector.connect()
            return source_connector.list_tables(source_schema)
        finally:
            if connect_attempted:
                self._close_connector(source_connector, "source")

    def prepare_target_tables(
        self,
        source_schema: str,
        target_schema: str,
        table_names: list[str] | None = None,
    ) -> list[TableSchemaPreparation]:
        """Create/refresh target schemas from source metadata without loading.

        This intentionally shares the same safe schema reconciliation used by
        ``execute``. It creates missing tables and adds missing source columns,
        but never truncates target data or drops existing columns.
        """
        self._validate_schema_name(source_schema, "source_schema")
        self._validate_schema_name(target_schema, "target_schema")

        source_connector = self._connection_resolver.resolve(
            self.source_connection_id
        )
        target_connector = self._connection_resolver.resolve(
            self.target_connection_id
        )
        source_connect_attempted = False
        target_connect_attempted = False
        try:
            source_connect_attempted = True
            source_connector.connect()
            target_connect_attempted = True
            target_connector.connect()
            self._prepare_target_schema(target_connector, target_schema)

            discovered_tables = source_connector.list_tables(source_schema)
            selected_tables = self._select_tables(
                discovered_tables,
                table_names,
            )
            preparations: list[TableSchemaPreparation] = []

            for table_name in selected_tables:
                preparation = TableSchemaPreparation(table_name=table_name)
                try:
                    preparation.target_was_created = not (
                        target_connector.table_exists(
                            target_schema,
                            table_name,
                        )
                    )
                    preparation.source_columns = (
                        self._extract_source_columns(
                            source_connector,
                            source_schema,
                            table_name,
                        )
                    )
                    if not preparation.source_columns:
                        raise ValueError(
                            f"No columns were discovered for "
                            f"{source_schema}.{table_name}."
                        )

                    assessment = self._ensure_target_table(
                        source_connector,
                        target_connector,
                        target_schema,
                        table_name,
                        preparation.source_columns,
                    )
                    preparation.schema_validation_status = (
                        assessment.schema_match_status
                    )
                    preparation.load_compatibility_status = (
                        "Compatible"
                        if assessment.is_compatible
                        else "Blocked"
                    )
                    if not assessment.is_compatible:
                        preparation.error_details = (
                            "Target schema is incompatible: "
                            + "; ".join(assessment.blocking_differences)
                        )
                    else:
                        preparation.target_columns = (
                            target_connector.list_columns(
                                target_schema,
                                table_name,
                            )
                        )
                except Exception as exc:
                    preparation.error_details = (
                        f"{type(exc).__name__}: {exc}"
                    )
                    logger.exception(
                        "Target schema preparation failed for %s.%s.",
                        target_schema,
                        table_name,
                    )
                preparations.append(preparation)

            return preparations
        finally:
            if target_connect_attempted:
                self._close_connector(target_connector, "target")
            if source_connect_attempted:
                self._close_connector(source_connector, "source")

    def execute(
        self,
        source_schema: str,
        target_schema: str,
        table_names: list[str] | None = None,
    ) -> MultiTableLoadSummary:
        """Discover and full-load selected tables, or every source table.

        ``source_schema`` selects the origin; ``target_schema`` selects the
        destination. Each source table is mapped to a target table with the
        same name in the destination schema.
        """
        self._validate_schema_name(source_schema, "source_schema")
        self._validate_schema_name(target_schema, "target_schema")

        started_at = self._now()
        source_connector = self._connection_resolver.resolve(
            self.source_connection_id
        )
        target_connector = self._connection_resolver.resolve(
            self.target_connection_id
        )
        summary = MultiTableLoadSummary(
            source_database=source_connector.metadata.database_name,
            target_database=target_connector.metadata.database_name,
            source_connection_name=source_connector.metadata.connection_name,
            target_connection_name=target_connector.metadata.connection_name,
            source_schema=source_schema,
            target_schema=target_schema,
            source_connection_id=self.source_connection_id,
            target_connection_id=self.target_connection_id,
            start_time=started_at,
        )
        source_connect_attempted = False
        target_connect_attempted = False

        try:
            logger.info(
                "Starting multi-table full load | source=%s.%s "
                "target=%s.%s",
                source_connector.metadata.database_name,
                source_schema,
                target_connector.metadata.database_name,
                target_schema,
            )
            source_connect_attempted = True
            source_connector.connect()
            target_connect_attempted = True
            target_connector.connect()

            # Discovery is always against the source; never infer table names
            # from the target schema or maintain a separate hardcoded list.
            source_tables = source_connector.list_tables(source_schema)
            summary.discovered_source_tables = list(source_tables)
            logger.info(
                "Discovered %d source tables in schema %s.",
                len(source_tables),
                source_schema,
            )

            # Restrict requested names to discovered source tables, while
            # retaining discovery order for predictable execution/reporting.
            selected_tables = self._select_tables(
                source_tables,
                table_names,
            )
            for table_name in selected_tables:
                result = self._load_table(
                    source_connector=source_connector,
                    target_connector=target_connector,
                    source_schema=source_schema,
                    target_schema=target_schema,
                    table_name=table_name,
                )
                summary.tables.append(result)

            summary.end_time = self._now()
            logger.info(
                "Multi-table full load completed: tables=%d succeeded=%d "
                "failed=%d rows_extracted=%d rows_loaded=%d",
                len(summary.tables),
                summary.succeeded,
                summary.failed,
                summary.total_rows_extracted,
                summary.total_rows_loaded,
            )
            return summary
        finally:
            if target_connect_attempted:
                self._close_connector(target_connector, "target")
            if source_connect_attempted:
                self._close_connector(source_connector, "source")

    @staticmethod
    def _select_tables(
        discovered_tables: list[str],
        requested_tables: list[str] | None,
    ) -> list[str]:
        """Choose all discovered tables or validate a requested subset."""
        if requested_tables is None:
            return discovered_tables
        if not requested_tables:
            raise ValueError("Select at least one table to load.")

        requested = list(dict.fromkeys(name.strip() for name in requested_tables))
        if any(not name for name in requested):
            raise ValueError("Selected table names must not be empty.")

        unknown_tables = [
            name for name in requested if name not in discovered_tables
        ]
        if unknown_tables:
            raise ValueError(
                "Selected tables were not found in the source schema: "
                + ", ".join(unknown_tables)
            )

        selected = set(requested)
        return [name for name in discovered_tables if name in selected]

    def _load_table(
        self,
        source_connector: BaseConnector,
        target_connector: BaseConnector,
        source_schema: str,
        target_schema: str,
        table_name: str,
    ) -> TableLoadResult:
        """Copy one source table into its same-named target table.

        Source metadata determines the column list and types. The same column
        names are used in the target schema; missing target columns are added
        before the data is inserted. Truncation and inserts run in a target
        transaction so a failed table can be rolled back independently.
        """
        result = TableLoadResult(
            table_name=table_name,
            start_time=self._now(),
        )
        transaction_started = False

        logger.info(
            "Starting full load for table %s.%s.",
            source_schema,
            table_name,
        )
        try:
            self._prepare_target_schema(target_connector, target_schema)
            columns = self._extract_source_columns(
                source_connector,
                source_schema,
                table_name,
            )
            result.primary_keys = self._extract_primary_keys(
                source_connector,
                source_schema,
                table_name,
            )
            if not columns:
                raise ValueError(
                    f"No columns were discovered for "
                    f"{source_schema}.{table_name}."
                )

            # This implementation uses identity mapping: source column names
            # also name their target columns, in source ordinal order.
            column_names = [column["column_name"] for column in columns]
            result.column_mappings = [
                {
                    "source_column": column["column_name"],
                    "target_column": column["column_name"],
                    "data_type": str(column.get("data_type", "")),
                    "ordinal_position": str(
                        column.get(
                            "ordinal_position",
                            column.get("ordinal_no", ""),
                        )
                    ),
                }
                for column in columns
            ]
            result.source_record_count = source_connector.count_rows(
                source_schema,
                table_name,
            )
            schema_assessment = self._ensure_target_table(
                source_connector,
                target_connector,
                target_schema,
                table_name,
                columns,
            )
            result.schema_validation_status = (
                schema_assessment.schema_match_status
            )
            result.load_compatibility_status = (
                "Compatible"
                if schema_assessment.is_compatible
                else "Blocked"
            )
            result.schema_differences = schema_assessment.schema_differences
            result.compatible_schema_differences = (
                schema_assessment.compatible_differences
            )
            if not schema_assessment.is_compatible:
                raise ValueError(
                    f"Schema metadata mismatch for target "
                    f"{target_schema}.{table_name}; target was not loaded: "
                    f"{'; '.join(schema_assessment.blocking_differences)}"
                )
            target_connector.begin_transaction()
            transaction_started = True
            target_connector.truncate_table(target_schema, table_name)

            select_columns = ", ".join(
                self._quote_identifier(name) for name in column_names
            )
            source_query = (
                f"SELECT {select_columns} "
                f"FROM {self._quote_identifier(source_schema)}."
                f"{self._quote_identifier(table_name)}"
            )
            for batch in source_connector.read_batches(
                query=source_query,
                batch_size=self.batch_size,
            ):
                result.rows_extracted += len(batch)
                result.rows_loaded += target_connector.write_batch(
                    target_schema=target_schema,
                    target_table=table_name,
                    column_names=column_names,
                    rows=batch,
                )

            result.target_record_count = target_connector.count_rows(
                target_schema,
                table_name,
            )
            if result.source_record_count != result.target_record_count:
                raise ValueError(
                    "Record-count validation failed: "
                    f"source={result.source_record_count}, "
                    f"target={result.target_record_count}."
                )

            target_connector.commit()
            transaction_started = False
            result.status = "Success"
        except Exception as exc:
            logger.exception("Full load failed for table %s.", table_name)
            result.error_details = f"{type(exc).__name__}: {exc}"
            if transaction_started:
                try:
                    target_connector.rollback()
                except Exception as rollback_exc:
                    logger.exception(
                        "Rollback failed for table %s.", table_name
                    )
                    result.error_details += (
                        f" Rollback failed: "
                        f"{type(rollback_exc).__name__}: {rollback_exc}"
                    )
            else:
                self._rollback_after_table_failure(
                    target_connector,
                    table_name,
                )
        finally:
            result.end_time = self._now()
            logger.info(
                "Table load finished | status=%s source=%s.%s "
                "target=%s.%s started=%s finished=%s extracted=%d "
                "loaded=%d source_count=%s target_count=%s error=%s",
                result.status,
                source_schema,
                result.table_name,
                target_schema,
                result.table_name,
                result.start_time,
                result.end_time,
                result.rows_extracted,
                result.rows_loaded,
                result.source_record_count,
                result.target_record_count,
                result.error_details,
            )
        return result

    @staticmethod
    def _extract_source_columns(
        source_connector: BaseConnector,
        schema_name: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        """Read source column names, types, and ordinal positions from metadata."""
        list_columns = getattr(source_connector, "list_columns", None)
        if not callable(list_columns):
            raise NotImplementedError(
                "The source connector does not support column discovery."
            )

        columns = list_columns(schema_name, table_name)
        return sorted(
            columns,
            key=lambda column: column.get(
                "ordinal_position",
                column.get("ordinal_no", 0),
            ),
        )

    def _extract_primary_keys(
        self,
        source_connector: BaseConnector,
        schema_name: str,
        table_name: str,
    ) -> list[str]:
        """Read primary-key columns for reporting and downstream use.

        Full-load insertion does not require a key, but recording it preserves
        source metadata that can support future incremental strategies.
        """
        schema_literal = self._quote_literal(schema_name)
        table_literal = self._quote_literal(table_name)
        query = f"""
            SELECT key_column.column_name
            FROM information_schema.table_constraints AS table_constraint
            JOIN information_schema.key_column_usage AS key_column
              ON key_column.constraint_catalog =
                 table_constraint.constraint_catalog
             AND key_column.constraint_schema =
                 table_constraint.constraint_schema
             AND key_column.constraint_name =
                 table_constraint.constraint_name
             AND key_column.table_schema = table_constraint.table_schema
             AND key_column.table_name = table_constraint.table_name
            WHERE table_constraint.constraint_type = 'PRIMARY KEY'
              AND table_constraint.table_schema = '{schema_literal}'
              AND table_constraint.table_name = '{table_literal}'
            ORDER BY key_column.ordinal_position;
        """
        return [
            str(row[0])
            for batch in source_connector.read_batches(
                query=query,
                batch_size=self.batch_size,
            )
            for row in batch
        ]

    @staticmethod
    def _prepare_target_schema(
        target_connector: BaseConnector,
        target_schema: str,
    ) -> None:
        """Create the destination schema when the configured schema is absent."""
        if not target_connector.schema_exists(target_schema):
            target_connector.create_schema(target_schema)
            target_connector.commit()

    def _ensure_target_table(
        self,
        source_connector: BaseConnector,
        target_connector: BaseConnector,
        target_schema: str,
        table_name: str,
        source_columns: list[dict[str, Any]],
    ) -> SchemaCompatibility:
        """Create missing targets and add newly discovered source columns.

        Existing target columns are never dropped or rewritten. Missing
        source columns are added before loading so newly added source fields
        are included in the same-name mapping and full-load insert.
        """
        created_target = not target_connector.table_exists(
            target_schema,
            table_name,
        )
        schema_transaction_started = False
        if created_target:
            if type(source_connector) is not type(target_connector):
                raise NotImplementedError(
                    "Automatic target-table creation requires matching "
                    "source and target connector implementations; no "
                    "cross-database datatype mapping is configured."
                )

            target_connector.begin_transaction()
            schema_transaction_started = True
        try:
            if created_target:
                target_connector.create_table(
                    target_schema,
                    table_name,
                    source_columns,
                )
                if not target_connector.table_exists(
                    target_schema,
                    table_name,
                ):
                    raise RuntimeError(
                        "Target connector did not create the requested "
                        f"table {target_schema}.{table_name}."
                    )

            list_columns = getattr(target_connector, "list_columns", None)
            if not callable(list_columns):
                raise NotImplementedError(
                    "The target connector does not support column discovery."
                )

            target_columns = list_columns(
                target_schema,
                table_name,
            )
            target_column_names = {
                column.get("column_name") for column in target_columns
            }
            missing_source_columns = [
                column
                for column in source_columns
                if column.get("column_name") not in target_column_names
            ]

            if missing_source_columns and not created_target:
                add_column = getattr(target_connector, "add_column", None)
                if not callable(add_column):
                    raise NotImplementedError(
                        "The target connector does not support adding "
                        "newly discovered source columns."
                    )

                # Adding a NOT NULL column to a populated target can fail
                # before the full-load transaction truncates its rows. Add
                # it nullable in that case; the source values are then
                # explicitly loaded into the column without losing target
                # data during schema preparation.
                target_has_rows = target_connector.count_rows(
                    target_schema,
                    table_name,
                ) > 0
                target_connector.begin_transaction()
                schema_transaction_started = True
                for source_column in missing_source_columns:
                    column_to_add = dict(source_column)
                    source_nullable = column_to_add.get("is_nullable")
                    source_is_not_nullable = (
                        source_nullable is False
                        or isinstance(source_nullable, str)
                        and source_nullable.strip().upper()
                        in {"NO", "FALSE", "0"}
                    )
                    if target_has_rows and source_is_not_nullable:
                        column_to_add["is_nullable"] = True
                    add_column(
                        target_schema,
                        table_name,
                        column_to_add,
                    )

                logger.info(
                    "Added source columns to target table %s.%s: %s",
                    target_schema,
                    table_name,
                    [
                        column.get("column_name")
                        for column in missing_source_columns
                    ],
                )

                # Re-read target metadata after ALTER TABLE so comparison
                # and loading use the actual destination schema.
                target_columns = list_columns(
                    target_schema,
                    table_name,
                )

            assessment = assess_column_compatibility(
                source_columns,
                target_columns,
                source_connector_code=(
                    source_connector.metadata.connector_code
                ),
                target_connector_code=(
                    target_connector.metadata.connector_code
                ),
            )
            if not assessment.is_compatible:
                if schema_transaction_started:
                    target_connector.rollback()
                    schema_transaction_started = False
                return assessment

            if missing_source_columns:
                assessment.compatible_differences.append(
                    "added source columns to target: "
                    + ", ".join(
                        str(column.get("column_name"))
                        for column in missing_source_columns
                    )
                )

            if schema_transaction_started:
                target_connector.commit()
                schema_transaction_started = False
            return assessment
        except Exception:
            if schema_transaction_started:
                target_connector.rollback()
            raise

    @staticmethod
    def _extract_column_names(columns: list[dict[str, Any]]) -> list[str]:
        """Return normalized column names in their declared ordinal order."""
        ordered_columns = sorted(
            columns,
            key=lambda column: column.get(
                "ordinal_position",
                column.get("ordinal_no", 0),
            ),
        )
        return [column["column_name"] for column in ordered_columns]

    @staticmethod
    def _rollback_after_table_failure(
        target_connector: BaseConnector,
        table_name: str,
    ) -> None:
        """Attempt rollback after a table failure outside an open transaction."""
        try:
            target_connector.rollback()
        except Exception:
            logger.exception(
                "Target cleanup rollback failed for table %s.",
                table_name,
            )

    @staticmethod
    def _close_connector(
        connector: BaseConnector,
        role: str,
    ) -> None:
        """Close a connector and log cleanup errors without hiding load results."""
        try:
            connector.close()
        except Exception:
            logger.exception("Failed to close the %s connector.", role)

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Quote a SQL identifier so schema/table/column names stay identifiers."""
        if not identifier or not identifier.strip():
            raise ValueError("SQL identifiers must not be empty.")
        return '"' + identifier.replace('"', '""') + '"'

    @staticmethod
    def _quote_literal(value: str) -> str:
        """Escape a value embedded in the metadata query's string literal."""
        return value.replace("'", "''")

    @staticmethod
    def _validate_schema_name(schema_name: str, parameter: str) -> None:
        """Reject empty schema configuration before opening database work."""
        if not schema_name or not schema_name.strip():
            raise ValueError(f"{parameter} must not be empty.")

    @staticmethod
    def _now() -> str:
        """Return a local timezone-aware timestamp for run/table tracking."""
        return datetime.now().astimezone().isoformat(timespec="seconds")


def main() -> None:
    """Parse CLI options, execute the schema-level load, and print its report."""
    parser = argparse.ArgumentParser(
        description=(
            "Dynamically discover and full-load all tables from a source "
            "schema into a target schema."
        )
    )
    # Source schema is the discovery/read location; target schema is the
    # destination for matching tables. They can differ between databases.
    parser.add_argument("--source-schema", default="public")
    parser.add_argument("--target-schema", default="warehouse")
    parser.add_argument("--source-connection-id", type=int, default=1)
    parser.add_argument("--target-connection-id", type=int, default=11)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the execution summary as JSON instead of a text report.",
    )
    arguments = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    summary = MultiTableFullLoadExecutor(
        source_connection_id=arguments.source_connection_id,
        target_connection_id=arguments.target_connection_id,
        batch_size=arguments.batch_size,
    ).execute(
        source_schema=arguments.source_schema,
        target_schema=arguments.target_schema,
    )
    if arguments.json:
        print(json.dumps(summary.to_dict(), indent=2))
    else:
        print(summary.render_report())
    if summary.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
