"""
Runtime Field Mapping Resolver
==============================

Purpose
-------
Resolves field-level source-to-target mappings from the metadata store.

Metadata flow
-------------

    map.mapping_field
            |
            | mapping_field_id
            v
    map.mapping_field_input
            |
            | source_field_id
            v
    catalog.dataset_field
            |
            v
    RuntimeFieldMapping

The target field is resolved from:

    map.mapping_field.target_field_id
            |
            v
    catalog.dataset_field

Why
---
The execution engine should not directly query metadata tables while
moving data.

This resolver converts the database metadata into immutable
RuntimeFieldMapping objects that can be consumed by the execution engine.

Important
---------
This component:

    - reads metadata only
    - does not connect to source databases
    - does not connect to target databases
    - does not read source data
    - does not write target data
    - does not modify metadata
"""

# Import the runtime field-level mapping model that this resolver creates.
from app.runtime.models import RuntimeFieldMapping

# Reuse the application's centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


class RuntimeFieldMappingResolver:
    """
    Resolves field-level mappings for a mapping version.

    The resolver is intentionally independent of source and target
    database connectors.

    Its only responsibility is translating metadata into runtime
    field-mapping objects.
    """

    def resolve(
        self,
        mapping_version_id: int,
        tenant_id: int,
    ) -> list[RuntimeFieldMapping]:
        """
        Resolve all field mappings for one mapping version.

        Parameters
        ----------
        mapping_version_id:
            Exact mapping version whose field mappings should be resolved.

        tenant_id:
            Tenant owning the mapping metadata.

        Returns
        -------
        list[RuntimeFieldMapping]
            Ordered source-to-target field mappings.

        Raises
        ------
        ValueError
            If the mapping version ID or tenant ID is invalid.

        LookupError
            If no field mappings are found.

        ValueError
            If metadata contains an invalid or inconsistent mapping.
        """

        # -------------------------------------------------------------
        # Validate the mapping version identifier before querying
        # PostgreSQL.
        # -------------------------------------------------------------
        if mapping_version_id <= 0:
            raise ValueError(
                "mapping_version_id must be greater than zero."
            )

        # -------------------------------------------------------------
        # Validate tenant ownership before querying tenant-scoped
        # metadata.
        # -------------------------------------------------------------
        if tenant_id <= 0:
            raise ValueError(
                "tenant_id must be greater than zero."
            )

        # -------------------------------------------------------------
        # Open the metadata-store connection.
        #
        # This connection is used only for metadata SELECT statements.
        # -------------------------------------------------------------
        with get_metastore_connection() as connection:

            # ---------------------------------------------------------
            # Create one cursor for the complete field-mapping query.
            # ---------------------------------------------------------
            with connection.cursor() as cursor:

                # -----------------------------------------------------
                # Resolve the complete source-to-target field mapping.
                #
                # Source side:
                #
                #   map.mapping_field_input.source_field_id
                #             |
                #             v
                #   catalog.dataset_field
                #
                # Target side:
                #
                #   map.mapping_field.target_field_id
                #             |
                #             v
                #   catalog.dataset_field
                #
                # We also validate tenant ownership at both mapping
                # levels.
                # -----------------------------------------------------
                cursor.execute(
                    """
                    SELECT
                        mf.mapping_field_id,
                        mfi.source_field_id,
                        source_field.field_name,
                        mf.target_field_id,
                        target_field.field_name,
                        mfi.source_alias,
                        mfi.input_role_code,
                        mf.mapping_type_code,
                        mf.ordinal_no

                    FROM map.mapping_field AS mf

                    INNER JOIN map.mapping_field_input AS mfi
                        ON mfi.mapping_field_id = mf.mapping_field_id
                       AND mfi.tenant_id = mf.tenant_id

                    INNER JOIN catalog.dataset_field AS source_field
                        ON source_field.field_id = mfi.source_field_id

                    INNER JOIN catalog.dataset_field AS target_field
                        ON target_field.field_id = mf.target_field_id

                    WHERE mf.mapping_version_id = %s
                      AND mf.tenant_id = %s

                    ORDER BY
                        mf.ordinal_no,
                        mfi.ordinal_no,
                        mf.mapping_field_id;
                    """,
                    (mapping_version_id, tenant_id),
                )

                # Fetch all resolved field mappings.
                rows = cursor.fetchall()

        # -------------------------------------------------------------
        # A mapping version without field mappings cannot perform a
        # metadata-driven data load.
        # -------------------------------------------------------------
        if not rows:
            raise LookupError(
                "No field mappings were found for mapping version "
                f"{mapping_version_id} and tenant {tenant_id}."
            )

        # -------------------------------------------------------------
        # Convert each metadata row into an immutable
        # RuntimeFieldMapping object.
        # -------------------------------------------------------------
        field_mappings: list[RuntimeFieldMapping] = []

        for row in rows:

            (
                mapping_field_id,
                source_field_id,
                source_field_name,
                target_field_id,
                target_field_name,
                source_alias,
                input_role_code,
                mapping_type_code,
                ordinal_no,
            ) = row

            # ---------------------------------------------------------
            # Validate the identifiers before constructing the runtime
            # object.
            # ---------------------------------------------------------
            if mapping_field_id <= 0:
                raise ValueError(
                    "Mapping metadata contains an invalid "
                    f"mapping_field_id: {mapping_field_id}"
                )

            if source_field_id <= 0:
                raise ValueError(
                    "Mapping metadata contains an invalid "
                    f"source_field_id: {source_field_id}"
                )

            if target_field_id <= 0:
                raise ValueError(
                    "Mapping metadata contains an invalid "
                    f"target_field_id: {target_field_id}"
                )

            if ordinal_no <= 0:
                raise ValueError(
                    "Mapping metadata contains an invalid ordinal: "
                    f"{ordinal_no}"
                )

            # ---------------------------------------------------------
            # Validate required field names.
            #
            # A physical source or target column cannot be resolved
            # if its metadata name is missing.
            # ---------------------------------------------------------
            if not source_field_name:
                raise ValueError(
                    "Source field name is missing for mapping field "
                    f"{mapping_field_id}."
                )

            if not target_field_name:
                raise ValueError(
                    "Target field name is missing for mapping field "
                    f"{mapping_field_id}."
                )

            # ---------------------------------------------------------
            # Validate the mapping behavior.
            #
            # The current Customer POC uses DIRECT mappings.
            # We preserve the metadata value instead of hardcoding
            # DIRECT so future mapping types can be supported.
            # ---------------------------------------------------------
            if not mapping_type_code:
                raise ValueError(
                    "Mapping type is missing for mapping field "
                    f"{mapping_field_id}."
                )

            # ---------------------------------------------------------
            # Create the immutable runtime mapping object.
            # ---------------------------------------------------------
            field_mapping = RuntimeFieldMapping(
                mapping_field_id=mapping_field_id,
                source_field_id=source_field_id,
                source_field_name=source_field_name,
                target_field_id=target_field_id,
                target_field_name=target_field_name,
                source_alias=source_alias,
                input_role_code=input_role_code,
                mapping_type_code=mapping_type_code,
                ordinal_no=ordinal_no,
            )

            # Add the resolved field mapping to the result collection.
            field_mappings.append(field_mapping)

        # -------------------------------------------------------------
        # Return the complete ordered runtime mapping collection.
        # -------------------------------------------------------------
        return field_mappings