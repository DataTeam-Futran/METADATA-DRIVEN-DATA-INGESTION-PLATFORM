
"""
Runtime Execution Context Resolver

Resolves execution metadata, physical source and target objects,
and their corresponding connectors.

This module does not execute data movement.
"""

from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.execution_context import RuntimeExecutionContext
from app.runtime.metadata_resolver import RuntimeMetadataResolver
from app.runtime.object_resolver import RuntimeObjectResolver


class RuntimeExecutionContextResolver:
    """Builds runtime execution contexts for pipeline tasks."""

    def __init__(
        self,
        metadata_resolver: RuntimeMetadataResolver | None = None,
        object_resolver: RuntimeObjectResolver | None = None,
        connection_resolver: RuntimeConnectionResolver | None = None,
    ) -> None:
        self._metadata_resolver = (
            metadata_resolver
            if metadata_resolver is not None
            else RuntimeMetadataResolver()
        )

        self._object_resolver = (
            object_resolver
            if object_resolver is not None
            else RuntimeObjectResolver()
        )

        self._connection_resolver = (
            connection_resolver
            if connection_resolver is not None
            else RuntimeConnectionResolver()
        )

    def resolve(
        self,
        pipeline_version_id: int,
        tenant_id: int,
        environment_id: int,
    ) -> RuntimeExecutionContext:
        """Resolve the context through the existing metadata resolver."""

        self._validate_scope(
            pipeline_version_id,
            tenant_id,
            environment_id,
        )

        execution_plan = self._metadata_resolver.resolve(
            pipeline_version_id=pipeline_version_id
        )

        return self.resolve_for_plan(
            execution_plan=execution_plan,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

    def resolve_objects_for_plan(
        self,
        execution_plan,
        tenant_id: int,
        environment_id: int,
    ):
        """Resolve physical source and target metadata without connectors."""

        if execution_plan is None:
            raise ValueError("execution_plan must not be None.")

        if tenant_id <= 0:
            raise ValueError("tenant_id must be greater than zero.")

        if environment_id <= 0:
            raise ValueError("environment_id must be greater than zero.")

        mapping = execution_plan.mapping

        if mapping.primary_source_dataset_id <= 0:
            raise ValueError(
                "Runtime mapping does not contain a valid "
                "primary source dataset ID."
            )

        if mapping.target_dataset_id <= 0:
            raise ValueError(
                "Runtime mapping does not contain a valid "
                "target dataset ID."
            )

        source_object = self._object_resolver.resolve(
            dataset_id=mapping.primary_source_dataset_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

        target_object = self._object_resolver.resolve(
            dataset_id=mapping.target_dataset_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

        return source_object, target_object

    def resolve_for_plan(
        self,
        execution_plan,
        tenant_id: int,
        environment_id: int,
    ) -> RuntimeExecutionContext:
        """Build a runtime context for one execution plan."""

        source_object, target_object = self.resolve_objects_for_plan(
            execution_plan=execution_plan,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

        source_connector = self._connection_resolver.resolve(
            source_object.connection_id
        )

        target_connector = self._connection_resolver.resolve(
            target_object.connection_id
        )

        if (
            source_connector.metadata.connection_id
            != source_object.connection_id
        ):
            raise ValueError(
                "Source connector connection ID does not match "
                "the source dataset binding."
            )

        if (
            target_connector.metadata.connection_id
            != target_object.connection_id
        ):
            raise ValueError(
                "Target connector connection ID does not match "
                "the target dataset binding."
            )

        return RuntimeExecutionContext(
            execution_plan=execution_plan,
            source_object=source_object,
            target_object=target_object,
            source_connector=source_connector,
            target_connector=target_connector,
        )

    @staticmethod
    def _validate_scope(
        pipeline_version_id: int,
        tenant_id: int,
        environment_id: int,
    ) -> None:
        """Validate the identifiers used for context resolution."""

        if pipeline_version_id <= 0:
            raise ValueError(
                "pipeline_version_id must be greater than zero."
            )

        if tenant_id <= 0:
            raise ValueError(
                "tenant_id must be greater than zero."
            )

        if environment_id <= 0:
            raise ValueError(
                "environment_id must be greater than zero."
            )
