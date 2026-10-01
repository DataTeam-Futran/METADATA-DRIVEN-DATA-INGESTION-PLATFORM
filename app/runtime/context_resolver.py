"""
Runtime Execution Context Resolver

Purpose
-------
Builds a complete RuntimeExecutionContext for an ingestion pipeline version.

The existing RuntimeMetadataResolver is responsible for resolving:

    Pipeline
    Pipeline Version
    Pipeline Task
    Mapping Version
    Load Configuration
    Target Load Configuration

Its existing public contract is:

    resolve(pipeline_version_id)

This module must respect that contract.

After resolving the execution plan, this module additionally resolves:

    Source Dataset
        -> Physical Source Object
        -> Source Connection
        -> Source Connector

    Target Dataset
        -> Physical Target Object
        -> Target Connection
        -> Target Connector

The final result is one RuntimeExecutionContext.

Important
---------
This module only resolves metadata and creates connector objects.

It does NOT:

    - open source database connections
    - open target database connections
    - truncate the target
    - read source rows
    - write target rows
    - modify metadata
"""

from app.runtime.connection_resolver import RuntimeConnectionResolver
from app.runtime.execution_context import RuntimeExecutionContext
from app.runtime.metadata_resolver import RuntimeMetadataResolver
from app.runtime.object_resolver import RuntimeObjectResolver


class RuntimeExecutionContextResolver:
    """
    Builds the complete runtime execution context.

    The resolver combines three existing runtime components:

        RuntimeMetadataResolver
        RuntimeObjectResolver
        RuntimeConnectionResolver

    The design keeps metadata resolution separate from physical execution.
    """

    def __init__(
        self,
        metadata_resolver: RuntimeMetadataResolver | None = None,
        object_resolver: RuntimeObjectResolver | None = None,
        connection_resolver: RuntimeConnectionResolver | None = None,
    ) -> None:
        """
        Initialize the runtime execution context resolver.

        Dependency injection is used so that the individual resolver
        components can later be replaced by test doubles or mocks.
        """

        # Resolve pipeline/task/mapping/load metadata.
        #
        # We reuse the existing implementation because it already knows
        # the correct deployed metadata schema.
        self._metadata_resolver = (
            metadata_resolver
            if metadata_resolver is not None
            else RuntimeMetadataResolver()
        )

        # Resolve logical dataset IDs into physical source/target objects.
        self._object_resolver = (
            object_resolver
            if object_resolver is not None
            else RuntimeObjectResolver()
        )

        # Resolve connection IDs into connector implementations.
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
        """
        Build the complete runtime execution context.

        Parameters
        ----------
        pipeline_version_id:
            Exact pipeline version that should be executed.

        tenant_id:
            Tenant owning the pipeline and datasets.

        environment_id:
            Environment used to resolve the physical dataset bindings.

        Returns
        -------
        RuntimeExecutionContext
            Complete immutable execution context.

        Notes
        -----
        The pipeline version ID is deliberately used instead of a combination
        of pipeline ID and version number.

        This is consistent with the existing RuntimeMetadataResolver contract
        and gives the runtime an exact immutable version to execute.
        """

        # Validate the pipeline version identifier before querying metadata.
        if pipeline_version_id <= 0:
            raise ValueError(
                "pipeline_version_id must be greater than zero."
            )

        # Validate the tenant identifier before resolving physical objects.
        if tenant_id <= 0:
            raise ValueError(
                "tenant_id must be greater than zero."
            )

        # Validate the environment identifier before resolving bindings.
        if environment_id <= 0:
            raise ValueError(
                "environment_id must be greater than zero."
            )

        # Resolve the complete execution plan using the EXISTING resolver
        # contract:
        #
        #     resolve(pipeline_version_id)
        #
        # Do not pass pipeline_id, tenant_id, or version number here because
        # RuntimeMetadataResolver does not accept those parameters.
        execution_plan = self._metadata_resolver.resolve(
            pipeline_version_id=pipeline_version_id
        )

        # The current Customer POC supports one executable task.
        #
        # RuntimeMetadataResolver already validates this condition and
        # returns the task inside the execution plan.
        task = execution_plan.task

        # Retrieve the mapping resolved by RuntimeMetadataResolver.
        mapping = execution_plan.mapping

        # Validate the source dataset ID before resolving its physical
        # binding.
        if mapping.primary_source_dataset_id <= 0:
            raise ValueError(
                "Runtime mapping does not contain a valid "
                "primary source dataset ID."
            )

        # Validate the target dataset ID before resolving its physical
        # binding.
        if mapping.target_dataset_id <= 0:
            raise ValueError(
                "Runtime mapping does not contain a valid target dataset ID."
            )

        # Resolve the logical source dataset to its physical object.
        #
        # Example for the Customer POC:
        #
        #     Dataset 7
        #         ->
        #     Connection 1
        #         ->
        #     demo_source_db.public.customer
        source_object = self._object_resolver.resolve(
            dataset_id=mapping.primary_source_dataset_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

        # Resolve the logical target dataset to its physical object.
        #
        # Example for the Customer POC:
        #
        #     Dataset 8
        #         ->
        #     Connection 11
        #         ->
        #     ingestion_metastore.warehouse.customer_target
        target_object = self._object_resolver.resolve(
            dataset_id=mapping.target_dataset_id,
            tenant_id=tenant_id,
            environment_id=environment_id,
        )

        # Resolve the source connection ID into the correct connector.
        #
        # The resolver obtains the connector type dynamically from metadata.
        source_connector = self._connection_resolver.resolve(
            source_object.connection_id
        )

        # Resolve the target connection ID into the correct connector.
        target_connector = self._connection_resolver.resolve(
            target_object.connection_id
        )

        # Protect against metadata inconsistencies where the connector
        # returned by the connection resolver does not correspond to the
        # dataset binding.
        if (
            source_connector.metadata.connection_id
            != source_object.connection_id
        ):
            raise ValueError(
                "Source connector connection ID does not match "
                "the source dataset binding."
            )

        # Perform the same consistency check for the target.
        if (
            target_connector.metadata.connection_id
            != target_object.connection_id
        ):
            raise ValueError(
                "Target connector connection ID does not match "
                "the target dataset binding."
            )

        # Build the final immutable runtime execution context.
        #
        # At this point we have:
        #
        #     - execution plan
        #     - source physical object
        #     - target physical object
        #     - source connector
        #     - target connector
        #
        # No physical database connection has been opened yet.
        return RuntimeExecutionContext(
            execution_plan=execution_plan,
            source_object=source_object,
            target_object=target_object,
            source_connector=source_connector,
            target_connector=target_connector,
        )