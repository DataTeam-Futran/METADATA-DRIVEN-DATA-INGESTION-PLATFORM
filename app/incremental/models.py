from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.runtime.object_resolver import RuntimeObject


@dataclass(frozen=True)
class ColumnMetadata:
    name: str
    data_type: str
    nullable: bool
    default_expression: str | None
    ordinal: int
    is_primary_key: bool


@dataclass(frozen=True)
class IncrementalTablePlan:
    mapping_version_id: int
    source_object: RuntimeObject
    target_object: RuntimeObject
    source_columns: tuple[str, ...]
    target_columns: tuple[str, ...]
    watermark_column: str
    primary_key_columns: tuple[str, ...]
    previous_watermark: Any
    initial_watermark: Any
    batch_size: int
    schema_strategy: str
    duplicate_strategy: str


@dataclass(frozen=True)
class IncrementalExecutionResult:
    execution_id: str
    status: str
    tables_processed: int
    rows_read: int
    rows_inserted: int
    rows_skipped: int
    execution_watermark: datetime
    watermark_updated: bool