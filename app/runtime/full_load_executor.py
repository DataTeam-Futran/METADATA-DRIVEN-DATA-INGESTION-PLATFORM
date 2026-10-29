
"""
Full Load Executor
==================

Executes a metadata-driven FULL LOAD from a source physical object
to a target physical object.

Supported execution pattern:
    FULL + TRUNCATE_INSERT + DIRECT field mappings

Features:
    - Source and target connection management
    - Physical schema and datatype validation
    - Batched source extraction and target insertion
    - Source-to-target row-count reconciliation
    - Transaction commit and rollback
    - Execution logging and exception classification
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg
import pyodbc

from app.connectors.base import BaseConnector
from app.runtime.execution_context import RuntimeExecutionContext
from app.runtime.models import RuntimeFieldMapping

from app.core.exceptions import (
    AuthorizationError,
    ConnectionResolutionError,
    DataQualityError,
    IngestionPlatformError,
    MappingResolutionError,
    MetadataResolutionError,
    NoSourceDataError,
    SchemaValidationError,
    SourceReadError,
    TargetWriteError,
    TransactionError,
)

logger = logging.getLogger(__name__)


class FullLoadExecutor:
    """Execute a metadata-driven FULL/TRUNCATE_INSERT load."""

    def execute(
        self,
        context: RuntimeExecutionContext,
        field_mappings: list[RuntimeFieldMapping],
    ) -> int:
        """Execute a full load and return the number of rows written."""

        # =========================================================
        # 1. INITIAL VALIDATION
        # =========================================================
        if context is None:
            raise MetadataResolutionError(
                "Runtime execution context is missing."
            )

        if not field_mappings:
            raise MappingResolutionError(
                "No active source-to-target field mappings were supplied."
            )

        # =========================================================
        # 2. READ EXECUTION CONFIGURATION
        # =========================================================
        try:
            execution_plan = context.execution_plan
            mapping = execution_plan.mapping
            load_config = execution_plan.load_config
            target_config = execution_plan.target_config
        except Exception as exc:
            raise MetadataResolutionError(
                "Required runtime execution configuration "
                "could not be resolved."
            ) from exc

        # Reserved for future target-specific configuration.
        _ = target_config

        # =========================================================
        # 3. VALIDATE LOAD TYPE AND STRATEGY
        # =========================================================
        if not mapping:
            raise MetadataResolutionError(
                "Execution mapping configuration is missing."
            )

        if mapping.load_type_code is None:
            raise MetadataResolutionError(
                "Load type is missing from execution configuration."
            )

        if mapping.load_strategy_code is None:
            raise MetadataResolutionError(
                "Load strategy is missing from execution configuration."
            )

        if mapping.load_type_code.upper() != "FULL":
            raise MetadataResolutionError(
                "FullLoadExecutor supports only FULL load. "
                f"Received load_type_code='{mapping.load_type_code}'."
            )

        if mapping.load_strategy_code.upper() != "TRUNCATE_INSERT":
            raise MetadataResolutionError(
                "FullLoadExecutor supports only TRUNCATE_INSERT strategy. "
                f"Received load_strategy_code="
                f"'{mapping.load_strategy_code}'."
            )

        # =========================================================
        # 4. VALIDATE LOAD CONFIGURATION
        # =========================================================
        if load_config is None:
            raise MetadataResolutionError(
                "Load configuration is missing."
            )

        if load_config.batch_size <= 0:
            raise DataQualityError(
                "Load configuration batch_size must be greater than zero."
            )

        if not load_config.truncate_before_load:
            raise DataQualityError(
                "TRUNCATE_INSERT requires truncate_before_load=True."
            )

        # =========================================================
        # 5. RESOLVE OBJECTS AND CONNECTORS
        # =========================================================
        source_object = context.source_object
        target_object = context.target_object
        source_connector = context.source_connector
        target_connector = context.target_connector

        if source_object is None:
            raise MetadataResolutionError(
                "Source physical object is missing from runtime context."
            )

        if target_object is None:
            raise MetadataResolutionError(
                "Target physical object is missing from runtime context."
            )

        if source_connector is None:
            raise ConnectionResolutionError(
                "Source connector is missing from runtime context."
            )

        if target_connector is None:
            raise ConnectionResolutionError(
                "Target connector is missing from runtime context."
            )

        # =========================================================
        # 6. VALIDATE PHYSICAL OBJECT INFORMATION
        # =========================================================
        if not source_object.schema_name:
            raise SchemaValidationError("Source schema is missing.")

        if not source_object.object_name:
            raise SchemaValidationError(
                "Source table/object name is missing."
            )

        if not target_object.schema_name:
            raise SchemaValidationError("Target schema is missing.")

        if not target_object.object_name:
            raise SchemaValidationError(
                "Target table/object name is missing."
            )

        # =========================================================
        # 7. VALIDATE AND ORDER FIELD MAPPINGS
        # =========================================================
        try:
            ordered_mappings = sorted(
                field_mappings,
                key=lambda item: item.ordinal_no,
            )
        except Exception as exc:
            raise MappingResolutionError(
                "Unable to order runtime field mappings."
            ) from exc

        if not ordered_mappings:
            raise MappingResolutionError(
                "No valid field mappings are available."
            )

        source_columns: list[str] = []
        target_columns: list[str] = []

        for mapping_item in ordered_mappings:
            if mapping_item is None:
                raise MappingResolutionError(
                    "Runtime field mapping contains a null mapping."
                )

            if not mapping_item.source_field_name:
                raise MappingResolutionError(
                    "A source field is missing from the runtime mapping."
                )

            if not mapping_item.target_field_name:
                raise MappingResolutionError(
                    "A target field is missing from the runtime mapping."
                )

            mapping_type = mapping_item.mapping_type_code

            if mapping_type is None or mapping_type.upper() != "DIRECT":
                raise MappingResolutionError(
                    "FullLoadExecutor currently supports only "
                    "DIRECT field mappings. "
                    f"Mapping field {mapping_item.mapping_field_id} "
                    f"uses '{mapping_type}'."
                )

            source_columns.append(mapping_item.source_field_name)
            target_columns.append(mapping_item.target_field_name)

        # =========================================================
        # 8. EXECUTION STATE
        # =========================================================
        total_rows_written = 0
        total_source_rows_read = 0
        batch_number = 0

        transaction_started = False
        source_connected = False
        target_connected = False

        # =========================================================
        # 9. CONNECT SOURCE
        # =========================================================
        try:
            source_connector.connect()
            source_connected = True

            logger.info("Source connection established.")

        except Exception as exc:
            raise ConnectionResolutionError(
                "Unable to establish source database connection."
            ) from exc

        # =========================================================
        # 10. CONNECT TARGET
        #
        # FIX: If target connection fails, close the source before
        # raising the error. The main finally block has not started
        # yet, so this cleanup must happen here.
        # =========================================================
        try:
            target_connector.connect()
            target_connected = True

            logger.info("Target connection established.")

        except Exception as exc:
            if source_connected:
                try:
                    source_connector.close()
                except Exception as close_exc:
                    logger.warning(
                        "Source connection cleanup failed after target "
                        "connection failure | exception_type=%s",
                        type(close_exc).__name__,
                    )
                finally:
                    source_connected = False

            raise ConnectionResolutionError(
                "Unable to establish target database connection."
            ) from exc

        # =========================================================
        # 11. MAIN EXECUTION
        # =========================================================
        try:
            # -----------------------------------------------------
            # 11A. PHYSICAL SCHEMA AND DATATYPE VALIDATION
            # -----------------------------------------------------
            # This must complete before source extraction and
            # before target transaction/TRUNCATE.
            self._validate_physical_schema(
                source_connector=source_connector,
                target_connector=target_connector,
                source_object=source_object,
                target_object=target_object,
                source_columns=source_columns,
                target_columns=target_columns,
            )

            # -----------------------------------------------------
            # 11B. BUILD SOURCE QUERY
            # -----------------------------------------------------
            select_columns = ", ".join(
                self._quote_identifier(column)
                for column in source_columns
            )

            source_schema = self._quote_identifier(
                source_object.schema_name
            )
            source_table = self._quote_identifier(
                source_object.object_name
            )

            source_query = (
                f"SELECT {select_columns} "
                f"FROM {source_schema}.{source_table}"
            )

            # -----------------------------------------------------
            # 11C. CHECK SOURCE DATA BEFORE TRUNCATE
            # -----------------------------------------------------
            try:
                source_batches = iter(
                    source_connector.read_batches(
                        query=source_query,
                        batch_size=load_config.batch_size,
                    )
                )

                first_batch = next(source_batches, None)

                if first_batch is None:
                    raise NoSourceDataError(
                        "Source returned zero records. "
                        "FULL load stopped before target TRUNCATE."
                    )

            except NoSourceDataError:
                raise
            except Exception as exc:
                raise SourceReadError(
                    "Unable to read source data during "
                    "pre-load source validation."
                ) from exc

            # -----------------------------------------------------
            # 11D. START TARGET TRANSACTION
            # -----------------------------------------------------
            try:
                target_connector.begin_transaction()
                transaction_started = True
            except Exception as exc:
                raise TransactionError(
                    "Unable to begin target transaction."
                ) from exc

            # -----------------------------------------------------
            # 11E. TRUNCATE TARGET
            # -----------------------------------------------------
            try:
                target_connector.truncate_table(
                    target_schema=target_object.schema_name,
                    target_table=target_object.object_name,
                )

            except psycopg.errors.LockNotAvailable as exc:
                raise TransactionError(
                    "Target TRUNCATE failed because the target table "
                    "is locked or the lock timeout was exceeded."
                ) from exc

            except Exception as exc:
                raise TargetWriteError(
                    "Target TRUNCATE operation failed."
                ) from exc

            # -----------------------------------------------------
            # 11F. WRITE FIRST SOURCE BATCH
            # -----------------------------------------------------
            batch_number = 1

            try:
                rows_written = target_connector.write_batch(
                    target_schema=target_object.schema_name,
                    target_table=target_object.object_name,
                    column_names=target_columns,
                    rows=first_batch,
                )

            except (
                psycopg.errors.InsufficientPrivilege,
                pyodbc.ProgrammingError,
            ) as exc:
                raise AuthorizationError(
                    "Permission denied for INSERT on target table."
                ) from exc

            except Exception as exc:
                raise TargetWriteError(
                    f"Target write failed at batch {batch_number}; "
                    f"rows_processed={total_rows_written}."
                ) from exc

            total_rows_written += rows_written
            total_source_rows_read += len(first_batch)

            # -----------------------------------------------------
            # 11G. WRITE REMAINING SOURCE BATCHES
            # -----------------------------------------------------
            try:
                for source_batch in source_batches:
                    batch_number += 1
                    total_source_rows_read += len(source_batch)

                    try:
                        rows_written = target_connector.write_batch(
                            target_schema=target_object.schema_name,
                            target_table=target_object.object_name,
                            column_names=target_columns,
                            rows=source_batch,
                        )

                    except psycopg.errors.InsufficientPrivilege as exc:
                        raise AuthorizationError(
                            "Permission denied for INSERT on target table."
                        ) from exc

                    except Exception as exc:
                        raise TargetWriteError(
                            f"Target write failed at batch {batch_number}; "
                            f"rows_processed={total_rows_written}."
                        ) from exc

                    total_rows_written += rows_written

            except (TargetWriteError, AuthorizationError):
                raise

            except Exception as exc:
                raise SourceReadError(
                    f"Source extraction failed at batch {batch_number}; "
                    f"rows_processed={total_rows_written}."
                ) from exc

            # -----------------------------------------------------
            # 11H. VALIDATE ZERO-WRITE CONDITION
            # -----------------------------------------------------
            if total_rows_written == 0:
                raise DataQualityError(
                    "Source data was available but no rows were "
                    "written to the target."
                )

            # -----------------------------------------------------
            # 11I. SOURCE-TO-TARGET ROW COUNT RECONCILIATION
            # -----------------------------------------------------
            try:
                target_row_count = target_connector.count_rows(
                    schema_name=target_object.schema_name,
                    table_name=target_object.object_name,
                )
            except Exception as exc:
                raise TargetWriteError(
                    "Unable to verify the target row count "
                    "after the full load."
                ) from exc

            logger.info(
                "Row-count reconciliation | "
                "source_rows_read=%s | target_rows=%s | rows_written=%s",
                total_source_rows_read,
                target_row_count,
                total_rows_written,
            )

            if total_source_rows_read != target_row_count:
                raise DataQualityError(
                    "Row-count reconciliation failed. "
                    f"source_rows_read={total_source_rows_read}, "
                    f"target_rows={target_row_count}, "
                    f"rows_written={total_rows_written}."
                )

            logger.info(
                "Row-count reconciliation passed | "
                "source_rows=%s | target_rows=%s",
                total_source_rows_read,
                target_row_count,
            )

            # -----------------------------------------------------
            # 11J. COMMIT
            # -----------------------------------------------------
            try:
                target_connector.commit()
                transaction_started = False
            except Exception as exc:
                raise TransactionError(
                    "Target transaction commit failed."
                ) from exc

            # -----------------------------------------------------
            # 11K. SUCCESS
            # -----------------------------------------------------
            logger.info(
                "FULL LOAD completed successfully | "
                "batches=%s | source_rows_read=%s | "
                "target_rows=%s | rows_written=%s",
                batch_number,
                total_source_rows_read,
                target_row_count,
                total_rows_written,
            )

            return total_rows_written

        # =========================================================
        # 12. KNOWN PLATFORM EXCEPTIONS
        # =========================================================
        except IngestionPlatformError as exc:
            if transaction_started and target_connected:
                try:
                    target_connector.rollback()
                except Exception as rollback_exc:
                    logger.exception(
                        "Target rollback failed | "
                        "original_exception=%s | rollback_exception=%s",
                        type(exc).__name__,
                        type(rollback_exc).__name__,
                    )

            logger.exception(
                "FULL LOAD failed | exception_type=%s | "
                "batch_number=%s | source_rows_read=%s | "
                "rows_processed=%s",
                type(exc).__name__,
                batch_number,
                total_source_rows_read,
                total_rows_written,
            )
            raise

        # =========================================================
        # 13. UNEXPECTED EXCEPTION
        # =========================================================
        except Exception as exc:
            if transaction_started and target_connected:
                try:
                    target_connector.rollback()
                except Exception as rollback_exc:
                    logger.exception(
                        "Target rollback failed | "
                        "original_exception=%s | rollback_exception=%s",
                        type(exc).__name__,
                        type(rollback_exc).__name__,
                    )

            logger.exception(
                "Unexpected FULL LOAD failure | "
                "exception_type=%s | batch_number=%s | "
                "source_rows_read=%s | rows_processed=%s",
                type(exc).__name__,
                batch_number,
                total_source_rows_read,
                total_rows_written,
            )

            raise IngestionPlatformError(
                "Unexpected FULL LOAD execution failure."
            ) from exc

        finally:
            # -----------------------------------------------------
            # 14. CLOSE TARGET
            # -----------------------------------------------------
            if target_connected:
                try:
                    target_connector.close()
                except Exception as exc:
                    logger.warning(
                        "Target connection cleanup failed | "
                        "exception_type=%s",
                        type(exc).__name__,
                    )

            # -----------------------------------------------------
            # 15. CLOSE SOURCE
            # -----------------------------------------------------
            if source_connected:
                try:
                    source_connector.close()
                except Exception as exc:
                    logger.warning(
                        "Source connection cleanup failed | "
                        "exception_type=%s",
                        type(exc).__name__,
                    )

    # =============================================================
    # DATATYPE COMPATIBILITY HELPERS
    # =============================================================

    @staticmethod
    def _get_type_family(data_type: str) -> str | None:
        """
        Classify supported PostgreSQL and SQL Server data types.

        Unknown types return None and are rejected until explicitly
        supported by a compatibility rule.
        """
        if not isinstance(data_type, str) or not data_type.strip():
            return None

        normalized = " ".join(data_type.strip().lower().split())

        type_families = {
            "string": {
                "text",
                "character varying",
                "varchar",
                "character",
                "char",
                "nvarchar",
                "nchar",
                "ntext",
                "national character varying",
                "national character",
            },
            "integer": {
                "smallint",
                "integer",
                "int",
                "bigint",
                "tinyint",
                "smallserial",
                "serial",
                "bigserial",
            },
            "decimal": {
                "numeric",
                "decimal",
                "money",
                "smallmoney",
            },
            "float": {
                "real",
                "float",
                "double precision",
            },
            "boolean": {
                "boolean",
                "bool",
                "bit",
            },
            "date": {
                "date",
            },
            "datetime": {
                "timestamp",
                "timestamp without time zone",
                "timestamp with time zone",
                "datetime",
                "datetime2",
                "smalldatetime",
                "datetimeoffset",
            },
            "time": {
                "time",
                "time without time zone",
                "time with time zone",
            },
            "binary": {
                "bytea",
                "binary",
                "varbinary",
                "image",
            },
            "uuid": {
                "uuid",
                "uniqueidentifier",
            },
        }

        for family, supported_types in type_families.items():
            if normalized in supported_types:
                return family

        return None

    @staticmethod
    def _are_types_compatible(
        source_type: str,
        target_type: str,
    ) -> bool:
        """
        Check broad datatype-family compatibility.

        This does not guarantee that values fit target length,
        precision, scale, numeric range, or timezone semantics.
        """
        source_family = FullLoadExecutor._get_type_family(source_type)
        target_family = FullLoadExecutor._get_type_family(target_type)

        return (
            source_family is not None
            and source_family == target_family
        )

    # =============================================================
    # PHYSICAL SCHEMA VALIDATION
    # =============================================================

    @staticmethod
    def _validate_physical_schema(
        source_connector: BaseConnector,
        target_connector: BaseConnector,
        source_object: Any,
        target_object: Any,
        source_columns: list[str],
        target_columns: list[str],
    ) -> None:
        """
        Validate mapped column existence and datatype compatibility.

        This method must finish before the target is truncated.
        """

        # SOURCE SCHEMA
        try:
            source_metadata = source_connector.list_columns(
                schema_name=source_object.schema_name,
                table_name=source_object.object_name,
            )
        except Exception as exc:
            raise SchemaValidationError(
                "Unable to retrieve source table schema."
            ) from exc

        source_metadata_by_name = {
            column["column_name"]: column
            for column in source_metadata
            if column.get("column_name")
        }

        missing_source_columns = [
            column
            for column in source_columns
            if column not in source_metadata_by_name
        ]

        if missing_source_columns:
            raise SchemaValidationError(
                "Source schema validation failed. "
                f"Missing source columns: {missing_source_columns}"
            )

        # TARGET SCHEMA
        try:
            target_metadata = target_connector.list_columns(
                schema_name=target_object.schema_name,
                table_name=target_object.object_name,
            )
        except Exception as exc:
            raise SchemaValidationError(
                "Unable to retrieve target table schema."
            ) from exc

        target_metadata_by_name = {
            column["column_name"]: column
            for column in target_metadata
            if column.get("column_name")
        }

        missing_target_columns = [
            column
            for column in target_columns
            if column not in target_metadata_by_name
        ]

        if missing_target_columns:
            raise SchemaValidationError(
                "Target schema validation failed. "
                f"Missing target columns: {missing_target_columns}"
            )

        # MAPPING VALIDATION
        if len(source_columns) != len(target_columns):
            raise SchemaValidationError(
                "Source and target mapping counts do not match."
            )

        # DATATYPE VALIDATION: FL-010
        for source_column, target_column in zip(
            source_columns,
            target_columns,
        ):
            source_column_metadata = source_metadata_by_name[
                source_column
            ]
            target_column_metadata = target_metadata_by_name[
                target_column
            ]

            source_type = source_column_metadata.get("data_type")
            target_type = target_column_metadata.get("data_type")

            if not isinstance(source_type, str) or not source_type.strip():
                raise SchemaValidationError(
                    "Source datatype metadata is missing or invalid. "
                    f"Source column='{source_column}'."
                )

            if not isinstance(target_type, str) or not target_type.strip():
                raise SchemaValidationError(
                    "Target datatype metadata is missing or invalid. "
                    f"Target column='{target_column}'."
                )

            if not FullLoadExecutor._are_types_compatible(
                source_type,
                target_type,
            ):
                raise SchemaValidationError(
                    "Source-to-target datatype mismatch or unsupported "
                    "datatype. "
                    f"Source column='{source_column}' "
                    f"(type='{source_type}'), "
                    f"Target column='{target_column}' "
                    f"(type='{target_type}'). "
                    "The load was stopped before target TRUNCATE."
                )

            logger.debug(
                "Datatype validation passed | source_column=%s | "
                "source_type=%s | target_column=%s | target_type=%s",
                source_column,
                source_type,
                target_column,
                target_type,
            )

    # =============================================================
    # SQL IDENTIFIER QUOTING
    # =============================================================

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        """Quote an SQL identifier using double quotes."""
        if not identifier or not identifier.strip():
            raise ValueError("SQL identifier must not be empty.")

        identifier = identifier.strip()
        escaped_identifier = identifier.replace('"', '""')

        return f'"{escaped_identifier}"'
