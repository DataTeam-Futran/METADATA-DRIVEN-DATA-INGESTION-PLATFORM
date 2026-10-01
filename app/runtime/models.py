"""
Runtime Execution Models
========================

Purpose
-------
Defines immutable Python objects used by the runtime engine.

These objects represent the execution plan resolved from metadata.

Why
---
The execution engine should not repeatedly query raw metadata tables while
performing data movement.

Instead:

    Metadata Database
          |
          v
    Runtime Metadata Resolver
          |
          v
    Runtime Execution Plan
          |
          v
    Execution Engine

The execution plan becomes the runtime contract for the current execution.
"""

# dataclass provides concise immutable-style data structures.
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeTask:
    """
    Represents one executable pipeline task.

    This object contains the orchestration information required to identify
    the mapping that should be executed.
    """

    # Database-generated task identifier.
    task_id: int

    # Human-readable task code.
    task_code: str

    # Human-readable task name.
    task_name: str

    # Runtime operation type, for example FULL_LOAD.
    task_type_code: str

    # Execution sequence inside the pipeline.
    sequence_no: int

    # Action to take when this task fails.
    on_failure_code: str

    # Optional retry policy.
    retry_policy_id: int | None

    # Maximum execution time for the task.
    timeout_seconds: int | None

    # Mapping version that defines the actual source-to-target behavior.
    mapping_version_id: int


@dataclass(frozen=True)
class RuntimeMapping:
    """
    Represents the mapping configuration required by the runtime engine.
    """

    # Mapping version identifier.
    mapping_version_id: int

    # Mapping identity.
    mapping_id: int

    # Mapping version number.
    version_no: int

    # Primary source dataset metadata identifier.
    primary_source_dataset_id: int

    # Source schema version metadata identifier.
    primary_source_schema_version_id: int

    # Target dataset metadata identifier.
    target_dataset_id: int

    # Target schema version metadata identifier.
    target_schema_version_id: int

    # Datatype mapping configuration identifier.
    datatype_mapping_set_id: int

    # Logical load type, for example FULL.
    load_type_code: str

    # Physical load strategy, for example TRUNCATE_INSERT.
    load_strategy_code: str

    # Current metadata lifecycle status.
    status_code: str

@dataclass(frozen=True)
class RuntimeFieldMapping:
    """
    Represents one resolved source-to-target field mapping.

    WHY:
    ----
    The metadata database stores field mappings across multiple
    tables such as:

        map.mapping_field
        map.mapping_field_input
        catalog.dataset_field

    The execution engine should not need to query those tables
    while data is being moved.

    This immutable object converts those metadata records into a
    simple runtime contract that the executor can consume.
    """

    # Unique mapping-field identifier.
    mapping_field_id: int

    # Source field metadata identifier.
    source_field_id: int

    # Physical/logical source column name.
    source_field_name: str

    # Target field metadata identifier.
    target_field_id: int

    # Physical/logical target column name.
    target_field_name: str

    # Alias used to identify the source in the mapping.
    source_alias: str | None

    # Role of this source input, for example PRIMARY.
    input_role_code: str | None

    # Mapping behavior, for example DIRECT.
    mapping_type_code: str

    # Field mapping execution order.
    ordinal_no: int

@dataclass(frozen=True)
class RuntimeLoadConfig:
    """
    Represents generic load execution settings.
    """

    # Load configuration identifier.
    load_config_id: int

    # Mapping version to which the configuration belongs.
    mapping_version_id: int

    # Runtime load type.
    load_type_code: str

    # Number of rows requested per source batch.
    batch_size: int

    # Whether the target should be truncated before loading.
    truncate_before_load: bool

    # Whether this configuration is active.
    is_active: bool


@dataclass(frozen=True)
class RuntimeTargetConfig:
    """
    Represents target-side execution behavior.
    """

    # Mapping version associated with this target configuration.
    mapping_version_id: int

    # Target write method.
    load_method_code: str

    # Optional target commit size.
    commit_size: int | None

    # Whether the runtime may automatically create the target.
    auto_create_target: bool

    # Policy controlling target structure changes.
    alter_target_policy_code: str

    # Target transaction behavior.
    transaction_mode_code: str

    # Maximum target write duration.
    write_timeout_seconds: int

    # Action performed before writing target data.
    target_prepare_action_code: str

    # Target schema handling policy.
    target_schema_policy_code: str

    # Constraint handling policy.
    constraint_apply_policy_code: str

    # Index handling policy.
    index_apply_policy_code: str


@dataclass(frozen=True)
class RuntimeExecutionPlan:
    """
    Complete execution plan resolved for one pipeline task.

    This is the object the future execution engine will consume.

    The execution engine should not need to know the internal layout of
    orch.*, map.*, or ingest.* tables after this object is constructed.
    """

    # Pipeline identity.
    pipeline_id: int

    # Pipeline version being executed.
    pipeline_version_id: int

    # Pipeline version number.
    pipeline_version_no: int

    # Pipeline version lifecycle status.
    pipeline_version_status: str

    # Pipeline code.
    pipeline_code: str

    # Pipeline name.
    pipeline_name: str

    # Resolved executable task.
    task: RuntimeTask

    # Resolved mapping configuration.
    mapping: RuntimeMapping

    # Generic load configuration.
    load_config: RuntimeLoadConfig

    # Target-specific configuration.
    target_config: RuntimeTargetConfig