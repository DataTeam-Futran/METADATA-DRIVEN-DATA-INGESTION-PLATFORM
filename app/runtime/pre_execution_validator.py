"""
Runtime Pre-Execution Validator
===============================

Performs read-only physical validation of source and target objects before
the ingestion engine is allowed to modify the target.

The validator uses metadata-resolved field mappings instead of hardcoded
column names.

Important:
    - Does not truncate or write target data.
    - May create a missing target table when its metadata policy allows it.
    - Never alters or drops an existing physical table.
    - Does not modify metadata.
    - Closes physical connections after validation.
"""

from dataclasses import dataclass

from app.runtime.execution_context import RuntimeExecutionContext
from app.runtime.models import RuntimeFieldMapping
from app.runtime.schema_comparison import compare_column_metadata


@dataclass(frozen=True)
class ValidationResult:
    """Result of one pre-execution validation check."""

    check_name: str
    passed: bool
    message: str


class PreExecutionValidator:
    """Validate physical source and target objects using field mappings."""

    def validate(
        self,
        context: RuntimeExecutionContext,
        field_mappings: list[RuntimeFieldMapping] | None = None,
    ) -> list[ValidationResult]:
        """
        Run read-only validation checks for one runtime execution context.

        Args:
            context:
                Fully resolved runtime execution context.
            field_mappings:
                Source-to-target mappings resolved from metadata.

        Returns:
            A list of successful validation results.

        Raises:
            ValueError:
                If mappings or execution configuration are invalid.
            LookupError:
                If a physical object or mapped column is missing.
        """

        # --------------------------------------------------------------
        # FIELD MAPPING VALIDATION
        # --------------------------------------------------------------

        if not field_mappings:
            raise ValueError(
                "Field mappings are required for pre-execution validation."
            )

        ordered_mappings = sorted(
            field_mappings,
            key=lambda mapping_item: mapping_item.ordinal_no,
        )

        expected_source_columns = [
            mapping.source_field_name
            for mapping in ordered_mappings
        ]

        expected_target_columns = [
            mapping.target_field_name
            for mapping in ordered_mappings
        ]

        if any(not column for column in expected_source_columns):
            raise ValueError(
                "Field mappings contain an empty source column name."
            )

        if any(not column for column in expected_target_columns):
            raise ValueError(
                "Field mappings contain an empty target column name."
            )

        if len(expected_source_columns) != len(set(expected_source_columns)):
            raise ValueError(
                "Field mappings contain duplicate source column names."
            )

        if len(expected_target_columns) != len(set(expected_target_columns)):
            raise ValueError(
                "Field mappings contain duplicate target column names."
            )

        results: list[ValidationResult] = []

        # --------------------------------------------------------------
        # SOURCE OBJECT VALIDATION
        # --------------------------------------------------------------

        source_connector = context.source_connector
        source_object = context.source_object

        source_connector.connect()

        try:
            source_table_exists = source_connector.table_exists(
                source_object.schema_name,
                source_object.object_name,
            )

            if not source_table_exists:
                raise LookupError(
                    "Source table was not found: "
                    f"{source_object.catalog_name}."
                    f"{source_object.schema_name}."
                    f"{source_object.object_name}"
                )

            results.append(
                ValidationResult(
                    check_name="SOURCE_OBJECT_EXISTS",
                    passed=True,
                    message=(
                        "Source object exists: "
                        f"{source_object.catalog_name}."
                        f"{source_object.schema_name}."
                        f"{source_object.object_name}"
                    ),
                )
            )

            # ----------------------------------------------------------
            # SOURCE MAPPED-COLUMN VALIDATION
            # ----------------------------------------------------------

            source_columns = source_connector.list_columns(
                source_object.schema_name,
                source_object.object_name,
            )

            if not source_columns:
                raise LookupError(
                    "Source table contains no columns: "
                    f"{source_object.schema_name}."
                    f"{source_object.object_name}"
                )

            source_column_names = [
                column["column_name"]
                for column in source_columns
            ]

            missing_source_columns = [
                column
                for column in expected_source_columns
                if column not in source_column_names
            ]

            if missing_source_columns:
                raise LookupError(
                    "Mapped source columns are missing: "
                    f"{missing_source_columns}"
                )

            results.append(
                ValidationResult(
                    check_name="SOURCE_COLUMNS",
                    passed=True,
                    message=(
                        "All mapped source columns are available: "
                        f"{expected_source_columns}"
                    ),
                )
            )

        finally:
            # Always close the source connection.
            source_connector.close()

        # --------------------------------------------------------------
        # TARGET OBJECT VALIDATION
        # --------------------------------------------------------------

        target_connector = context.target_connector
        target_object = context.target_object
        target_config = context.execution_plan.target_config

        target_connector.connect()

        try:
            target_table_exists = target_connector.table_exists(
                target_object.schema_name,
                target_object.object_name,
            )

            if not target_table_exists:
                if (
                    not target_config.auto_create_target
                    or target_config.target_schema_policy_code
                    != "CREATE_IF_MISSING"
                ):
                    raise LookupError(
                        "Target table was not found and target-load "
                        "metadata does not permit creation: "
                        f"{target_object.catalog_name}."
                        f"{target_object.schema_name}."
                        f"{target_object.object_name}"
                    )

                if type(source_connector) is not type(target_connector):
                    raise ValueError(
                        "Automatic target-table creation requires matching "
                        "source and target connector implementations; a "
                        "configured cross-database datatype mapping is "
                        "required otherwise."
                    )

                source_columns_by_name = {
                    column["column_name"]: column
                    for column in source_columns
                }
                target_column_definitions = []
                for ordinal, mapping in enumerate(
                    ordered_mappings,
                    start=1,
                ):
                    source_column = source_columns_by_name.get(
                        mapping.source_field_name
                    )
                    if source_column is None:
                        raise LookupError(
                            "Cannot create target table because mapped "
                            "source column is missing: "
                            f"{mapping.source_field_name}"
                        )

                    target_column = dict(source_column)
                    target_column["column_name"] = (
                        mapping.target_field_name
                    )
                    target_column["ordinal_position"] = ordinal
                    target_column_definitions.append(target_column)

                target_connector.begin_transaction()
                try:
                    target_connector.create_table(
                        target_object.schema_name,
                        target_object.object_name,
                        target_column_definitions,
                    )

                    # Refresh metadata after DDL and validate before
                    # committing the new table.
                    target_table_exists = target_connector.table_exists(
                        target_object.schema_name,
                        target_object.object_name,
                    )
                    if not target_table_exists:
                        raise RuntimeError(
                            "Target connector did not create the configured "
                            "target table."
                        )

                    created_target_columns = (
                        target_connector.list_columns(
                            target_object.schema_name,
                            target_object.object_name,
                        )
                    )
                    creation_differences = compare_column_metadata(
                        source_columns,
                        created_target_columns,
                        include_defaults=False,
                    )
                    if creation_differences:
                        raise ValueError(
                            "Created target schema does not match the "
                            "source schema: "
                            + "; ".join(creation_differences)
                        )

                    target_connector.commit()
                except Exception:
                    target_connector.rollback()
                    raise

            results.append(
                ValidationResult(
                    check_name="TARGET_OBJECT_EXISTS",
                    passed=True,
                    message=(
                        "Target object exists: "
                        f"{target_object.catalog_name}."
                        f"{target_object.schema_name}."
                        f"{target_object.object_name}"
                    ),
                )
            )

            # ----------------------------------------------------------
            # TARGET MAPPED-COLUMN VALIDATION
            # ----------------------------------------------------------

            target_columns = target_connector.list_columns(
                target_object.schema_name,
                target_object.object_name,
            )

            if not target_columns:
                raise LookupError(
                    "Target table contains no columns: "
                    f"{target_object.schema_name}."
                    f"{target_object.object_name}"
                )

            target_column_names = [
                column["column_name"]
                for column in target_columns
            ]

            missing_target_columns = [
                column
                for column in expected_target_columns
                if column not in target_column_names
            ]

            if missing_target_columns:
                raise LookupError(
                    "Mapped target columns are missing: "
                    f"{missing_target_columns}"
                )

            results.append(
                ValidationResult(
                    check_name="TARGET_COLUMNS",
                    passed=True,
                    message=(
                        "All mapped target columns are available: "
                        f"{expected_target_columns}"
                    ),
                )
            )

            schema_differences = compare_column_metadata(
                source_columns,
                target_columns,
                include_defaults=False,
            )
            results.append(
                ValidationResult(
                    check_name="SCHEMA_METADATA_MATCH",
                    passed=not schema_differences,
                    message=(
                        "; ".join(schema_differences)
                        if schema_differences
                        else (
                            "Source and target column metadata match "
                            "(names, order, types, nullability, precision, "
                            "scale, defaults, and supported attributes)."
                        )
                    ),
                )
            )

        finally:
            # Always close the target connection.
            target_connector.close()

        # --------------------------------------------------------------
        # EXECUTION CONFIGURATION VALIDATION
        # --------------------------------------------------------------

        mapping = context.execution_plan.mapping
        load_config = context.execution_plan.load_config
        target_config = context.execution_plan.target_config

        if mapping.load_type_code != "FULL":
            raise ValueError(
                "Pre-execution validator currently supports FULL load only, "
                f"received: {mapping.load_type_code}"
            )

        if mapping.load_strategy_code != "TRUNCATE_INSERT":
            raise ValueError(
                "Pre-execution validator currently supports TRUNCATE_INSERT "
                f"only, received: {mapping.load_strategy_code}"
            )

        if load_config.batch_size <= 0:
            raise ValueError(
                "Batch size must be greater than zero."
            )

        if not load_config.is_active:
            raise ValueError(
                "Load configuration is inactive."
            )

        results.append(
            ValidationResult(
                check_name="EXECUTION_CONFIGURATION",
                passed=True,
                message=(
                    "FULL / TRUNCATE_INSERT configuration is valid."
                ),
            )
        )

        return results