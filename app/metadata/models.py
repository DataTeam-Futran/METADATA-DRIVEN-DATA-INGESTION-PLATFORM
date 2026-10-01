from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LoadMetadata:
    mapping_version_id: int
    load_type: str
    batch_size: int
    truncate_before_load: bool


@dataclass(frozen=True)
class SourceMetadata:
    source_id: int
    connection_id: int
    dataset_id: int
    dataset_name: str
    source_name: str
    source_type: str
    database_name: str
    schema_name: str
    object_name: str


@dataclass(frozen=True)
class SourceFieldMetadata:
    schema_field_id: int
    ordinal_position: int
    column_name: str
    native_data_type: str
    data_length: Optional[int]
    numeric_precision: Optional[int]
    numeric_scale: Optional[int]
    is_nullable: bool
    is_primary_key: bool


@dataclass(frozen=True)
class MappingFieldMetadata:
    mapping_field_id: int
    source_field_name: str
    target_field_name: str
    target_data_type: str
    transformation_type: Optional[str]
    transformation_expression: Optional[str]
    is_key: bool
    is_required: bool
    ordinal_position: int


@dataclass(frozen=True)
class TargetMetadata:
    target_id: int
    connection_id: int
    target_name: str
    target_type: str
    database_name: str
    schema_name: str
    object_name: str


@dataclass(frozen=True)
class ExecutionMetadata:
    load: LoadMetadata
    source: SourceMetadata
    source_fields: tuple[SourceFieldMetadata, ...]
    mapping_fields: tuple[MappingFieldMetadata, ...]
    target: TargetMetadata