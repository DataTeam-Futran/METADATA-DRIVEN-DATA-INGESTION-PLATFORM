from app.db.metastore import get_metastore_connection
from app.metadata.models import (
    ExecutionMetadata,
    LoadMetadata,
    MappingFieldMetadata,
    SourceFieldMetadata,
    SourceMetadata,
    TargetMetadata,
)


class MetadataResolver:
    """
    Resolves persisted ingestion metadata into an execution-ready
    ExecutionMetadata object.

    This class contains metadata-resolution logic only.
    It does not connect to source/target databases and does not
    execute ingestion.
    """

    def resolve(self, mapping_version_id: int) -> ExecutionMetadata:
        if mapping_version_id <= 0:
            raise ValueError("mapping_version_id must be greater than zero")

        with get_metastore_connection() as connection:
            load_metadata = self._resolve_load_metadata(
                connection,
                mapping_version_id,
            )

            mapping_version = self._resolve_mapping_version(
                connection,
                mapping_version_id,
            )

            source_metadata = self._resolve_source_metadata(
                connection,
                mapping_version,
            )

            source_fields = self._resolve_source_fields(
                connection,
                mapping_version["source_schema_version_id"],
            )

            mapping_fields = self._resolve_mapping_fields(
                connection,
                mapping_version_id,
            )

            target_metadata = self._resolve_target_metadata(
                connection,
                mapping_version["mapping_id"],
            )

        self._validate_metadata(
            load_metadata=load_metadata,
            source_metadata=source_metadata,
            source_fields=source_fields,
            mapping_fields=mapping_fields,
            target_metadata=target_metadata,
        )

        return ExecutionMetadata(
            load=load_metadata,
            source=source_metadata,
            source_fields=tuple(source_fields),
            mapping_fields=tuple(mapping_fields),
            target=target_metadata,
        )

    # ------------------------------------------------------------------
    # LOAD CONFIGURATION
    # ------------------------------------------------------------------

    def _resolve_load_metadata(
        self,
        connection,
        mapping_version_id: int,
    ) -> LoadMetadata:

        query = """
            SELECT
                mapping_version_id,
                load_type_code,
                batch_size,
                truncate_before_load
            FROM ingest.load_config
            WHERE mapping_version_id = %s
              AND is_active = TRUE
            LIMIT 1;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (mapping_version_id,))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(
                f"No active load configuration found for "
                f"mapping_version_id={mapping_version_id}"
            )

        return LoadMetadata(
            mapping_version_id=row[0],
            load_type=row[1],
            batch_size=row[2],
            truncate_before_load=row[3],
        )

    # ------------------------------------------------------------------
    # MAPPING VERSION
    # ------------------------------------------------------------------

    def _resolve_mapping_version(
        self,
        connection,
        mapping_version_id: int,
    ) -> dict:

        query = """
            SELECT
                mapping_version_id,
                mapping_id,
                source_schema_version_id,
                target_schema_version_id,
                version_number,
                status
            FROM ingest.mapping_version
            WHERE mapping_version_id = %s
            LIMIT 1;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (mapping_version_id,))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(
                f"Mapping version {mapping_version_id} was not found"
            )

        return {
            "mapping_version_id": row[0],
            "mapping_id": row[1],
            "source_schema_version_id": row[2],
            "target_schema_version_id": row[3],
            "version_number": row[4],
            "status": row[5],
        }

    # ------------------------------------------------------------------
    # SOURCE METADATA
    # ------------------------------------------------------------------

    def _resolve_source_metadata(
        self,
        connection,
        mapping_version: dict,
    ) -> SourceMetadata:

        query = """
            SELECT
                s.source_id,
                s.connection_id,
                d.dataset_id,
                d.dataset_name,
                s.source_name,
                s.source_type,
                s.source_database,
                s.source_schema,
                s.source_object
            FROM ingest.mapping_version mv
            INNER JOIN ingest.dataset d
                ON d.dataset_id = (
                    SELECT dataset_id
                    FROM ingest.mapping
                    WHERE mapping_id = mv.mapping_id
                )
            INNER JOIN ingest.source_config s
                ON s.source_id = d.source_id
            WHERE mv.mapping_version_id = %s
            LIMIT 1;
        """

        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (mapping_version["mapping_version_id"],),
            )
            row = cursor.fetchone()

        if row is None:
            raise LookupError(
                f"Source metadata could not be resolved for "
                f"mapping_version_id="
                f"{mapping_version['mapping_version_id']}"
            )

        return SourceMetadata(
            source_id=row[0],
            connection_id=row[1],
            dataset_id=row[2],
            dataset_name=row[3],
            source_name=row[4],
            source_type=row[5],
            database_name=row[6],
            schema_name=row[7],
            object_name=row[8],
        )

    # ------------------------------------------------------------------
    # SOURCE FIELDS
    # ------------------------------------------------------------------

    def _resolve_source_fields(
        self,
        connection,
        schema_version_id: int,
    ) -> list[SourceFieldMetadata]:

        if schema_version_id is None:
            raise ValueError(
                "Source schema version is required for metadata resolution"
            )

        query = """
            SELECT
                schema_field_id,
                ordinal_position,
                column_name,
                native_data_type,
                data_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                is_primary_key
            FROM ingest.schema_field
            WHERE schema_version_id = %s
            ORDER BY ordinal_position;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (schema_version_id,))
            rows = cursor.fetchall()

        if not rows:
            raise LookupError(
                f"No source fields found for "
                f"schema_version_id={schema_version_id}"
            )

        return [
            SourceFieldMetadata(
                schema_field_id=row[0],
                ordinal_position=row[1],
                column_name=row[2],
                native_data_type=row[3],
                data_length=row[4],
                numeric_precision=row[5],
                numeric_scale=row[6],
                is_nullable=row[7],
                is_primary_key=row[8],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # MAPPING FIELDS
    # ------------------------------------------------------------------

    def _resolve_mapping_fields(
        self,
        connection,
        mapping_version_id: int,
    ) -> list[MappingFieldMetadata]:

        query = """
            SELECT
                mapping_field_id,
                source_field_name,
                target_field_name,
                target_data_type,
                transformation_type,
                transformation_expression,
                is_key,
                is_required,
                ordinal_position
            FROM ingest.mapping_field
            WHERE mapping_version_id = %s
            ORDER BY ordinal_position, mapping_field_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (mapping_version_id,))
            rows = cursor.fetchall()

        if not rows:
            raise LookupError(
                f"No mapping fields found for "
                f"mapping_version_id={mapping_version_id}"
            )

        return [
            MappingFieldMetadata(
                mapping_field_id=row[0],
                source_field_name=row[1],
                target_field_name=row[2],
                target_data_type=row[3],
                transformation_type=row[4],
                transformation_expression=row[5],
                is_key=row[6],
                is_required=row[7],
                ordinal_position=row[8],
            )
            for row in rows
        ]

    # ------------------------------------------------------------------
    # TARGET METADATA
    # ------------------------------------------------------------------

    def _resolve_target_metadata(
        self,
        connection,
        mapping_id: int,
    ) -> TargetMetadata:

        query = """
            SELECT
                t.target_id,
                t.connection_id,
                t.target_name,
                t.target_type,
                t.target_database,
                t.target_schema,
                t.target_object
            FROM ingest.mapping m
            INNER JOIN ingest.dataset d
                ON d.dataset_id = m.dataset_id
            INNER JOIN ingest.target_config t
                ON t.target_id = d.target_id
            WHERE m.mapping_id = %s
            LIMIT 1;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (mapping_id,))
            row = cursor.fetchone()

        if row is None:
            raise LookupError(
                f"Target metadata could not be resolved for "
                f"mapping_id={mapping_id}"
            )

        return TargetMetadata(
            target_id=row[0],
            connection_id=row[1],
            target_name=row[2],
            target_type=row[3],
            database_name=row[4],
            schema_name=row[5],
            object_name=row[6],
        )

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def _validate_metadata(
        self,
        load_metadata: LoadMetadata,
        source_metadata: SourceMetadata,
        source_fields: list[SourceFieldMetadata],
        mapping_fields: list[MappingFieldMetadata],
        target_metadata: TargetMetadata,
    ) -> None:

        if load_metadata.load_type != "FULL_LOAD":
            raise ValueError(
                f"Expected FULL_LOAD for current POC, "
                f"received {load_metadata.load_type}"
            )

        if load_metadata.batch_size <= 0:
            raise ValueError(
                "Load batch_size must be greater than zero"
            )

        source_field_names = {
            field.column_name
            for field in source_fields
        }

        for mapping_field in mapping_fields:
            if mapping_field.source_field_name not in source_field_names:
                raise ValueError(
                    f"Mapping references source field "
                    f"'{mapping_field.source_field_name}', "
                    f"but that field does not exist in the "
                    f"source schema"
                )

        target_fields = {
            field.target_field_name
            for field in mapping_fields
        }

        if len(target_fields) != len(mapping_fields):
            raise ValueError(
                "Duplicate target fields detected in mapping metadata"
            )

        if not source_metadata.database_name:
            raise ValueError("Source database is missing")

        if not source_metadata.schema_name:
            raise ValueError("Source schema is missing")

        if not source_metadata.object_name:
            raise ValueError("Source object is missing")

        if not target_metadata.database_name:
            raise ValueError("Target database is missing")

        if not target_metadata.schema_name:
            raise ValueError("Target schema is missing")

        if not target_metadata.object_name:
            raise ValueError("Target object is missing")