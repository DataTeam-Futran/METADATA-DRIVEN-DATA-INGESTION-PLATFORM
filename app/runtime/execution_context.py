"""
Runtime Execution Context

Purpose
-------
This module combines all metadata and runtime objects required to execute
one ingestion task.

The execution context is intentionally immutable.

Once created, the execution engine receives a complete execution context
and does not need to repeatedly query the metadata store.

Runtime context contains:

    1. Runtime execution plan
    2. Source physical object
    3. Target physical object
    4. Source connector
    5. Target connector

Important
---------
Creating this context does NOT open physical database connections.

Connectors are created only. The execution engine will explicitly call
connect() when it is ready to perform the actual ingestion.
"""

from dataclasses import dataclass

from app.connectors.base import BaseConnector
from app.runtime.models import RuntimeExecutionPlan
from app.runtime.object_resolver import RuntimeObject


@dataclass(frozen=True)
class RuntimeExecutionContext:
    """
    Complete runtime information required for executing one ingestion task.

    The context is immutable so that the execution engine cannot accidentally
    modify execution metadata while a load is running.
    """

    # Complete execution plan resolved from orchestration, mapping, and
    # ingestion metadata.
    execution_plan: RuntimeExecutionPlan

    # Physical source object resolved from catalog.dataset_binding.
    source_object: RuntimeObject

    # Physical target object resolved from catalog.dataset_binding.
    target_object: RuntimeObject

    # Connector responsible for reading the source.
    source_connector: BaseConnector

    # Connector responsible for writing to the target.
    target_connector: BaseConnector