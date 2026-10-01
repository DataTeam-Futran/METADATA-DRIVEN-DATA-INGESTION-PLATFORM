"""
Runtime Pre-Execution Validator

Purpose
-------
Performs read-only physical validation before the ingestion engine is
allowed to modify the target.

The validator receives a fully resolved RuntimeExecutionContext containing:

    - Runtime execution plan
    - Source physical object
    - Target physical object
    - Source connector
    - Target connector

The validator checks:

    1. Source connection can be established.
    2. Target connection can be established.
    3. Source table exists.
    4. Target table exists.
    5. Source columns are available.
    6. Target columns are available.
    7. Source and target columns match the expected mapping.

Important
---------
This validator is READ ONLY.

It does NOT:

    - truncate the target
    - insert rows
    - update rows
    - delete rows
    - create tables
    - alter tables
    - modify metadata

Physical connections are closed after validation.
"""

from dataclasses import dataclass

from app.runtime.execution_context import RuntimeExecutionContext


@dataclass(frozen=True)
class ValidationResult:
    """
    Represents the result of one pre-execution validation check.

    A structured result is used instead of returning only True/False so
    that the execution layer can later expose useful operational evidence.
    """

    # Human-readable name of the validation check.
    check_name: str

    # Whether the validation succeeded.
    passed: bool

    # Additional information explaining the result.
    message: str


class PreExecutionValidator:
    """
    Performs read-only validation against the physical source and target.

    The validator deliberately receives a RuntimeExecutionContext instead
    of resolving metadata itself.

    This maintains the separation:

        Metadata Resolution
                ↓
        Runtime Context
                ↓
        Pre-Execution Validation
                ↓
        Data Execution
    """

    def validate(
        self,
        context: RuntimeExecutionContext,
    ) -> list[ValidationResult]:
        """
        Execute all pre-load validation checks.

        Parameters
        ----------
        context:
            Fully resolved runtime execution context.

        Returns
        -------
        list[ValidationResult]
            Individual validation results.

        Raises
        ------
        Exception
            Physical connection or validation failures are propagated to
            the caller so that execution cannot continue accidentally.
        """

        # Store individual validation results so the caller can display
        # exactly which checks passed.
        results: list[ValidationResult] = []

        # --------------------------------------------------------------
        # SOURCE VALIDATION
        # --------------------------------------------------------------

        # Retrieve the source connector from the already resolved context.
        source_connector = context.source_connector

        # Retrieve the source physical object.
        source_object = context.source_object

        # Connect to the source database.
        #
        # This is the first point in our runtime flow where a physical
        # database connection is intentionally opened.
        source_connection = source_connector.connect()

        try:
            # Validate that the expected source object exists.
            #
            # We use information_schema because it provides a standard
            # metadata interface for PostgreSQL and many relational
            # database connectors can implement equivalent logic later.
            source_query = """
                SELECT 1
                FROM information_schema.tables
                WHERE table_catalog = %s
                  AND table_schema = %s
                  AND table_name = %s
                LIMIT 1;
            """

            with source_connection.cursor() as cursor:
                cursor.execute(
                    source_query,
                    (
                        source_connector.metadata.database_name,
                        source_object.schema_name,
                        source_object.object_name,
                    ),
                )

                source_table_exists = cursor.fetchone() is not None

            # Stop execution if the source table does not exist.
            if not source_table_exists:
                raise LookupError(
                    "Source table was not found: "
                    f"{source_object.catalog_name}."
                    f"{source_object.schema_name}."
                    f"{source_object.object_name}"
                )

            # Record the successful source-object validation.
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
            # SOURCE COLUMN VALIDATION
            # ----------------------------------------------------------
            #
            # Retrieve source columns in ordinal order.
            source_columns_query = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    ordinal_position
                FROM information_schema.columns
                WHERE table_catalog = %s
                  AND table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
            """

            with source_connection.cursor() as cursor:
                cursor.execute(
                    source_columns_query,
                    (
                        source_connector.metadata.database_name,
                        source_object.schema_name,
                        source_object.object_name,
                    ),
                )

                source_columns = cursor.fetchall()

            # A source table without columns cannot be loaded.
            if not source_columns:
                raise LookupError(
                    "Source table contains no columns: "
                    f"{source_object.schema_name}."
                    f"{source_object.object_name}"
                )

            # Convert the database result into a simple ordered list of
            # column names for validation.
            source_column_names = [
                row[0]
                for row in source_columns
            ]

            # The Customer POC mapping expects these four source columns.
            expected_source_columns = [
                "customer_id",
                "customer_name",
                "email",
                "city",
            ]

            # Validate that every expected source field exists.
            missing_source_columns = [
                column
                for column in expected_source_columns
                if column not in source_column_names
            ]

            if missing_source_columns:
                raise LookupError(
                    "Required source columns are missing: "
                    f"{missing_source_columns}"
                )

            # Record the successful source-column validation.
            results.append(
                ValidationResult(
                    check_name="SOURCE_COLUMNS",
                    passed=True,
                    message=(
                        "Required source columns are available: "
                        f"{expected_source_columns}"
                    ),
                )
            )

        finally:
            # Always close the source connector after validation.
            #
            # This guarantees that the pre-execution validator does not
            # leave an unused physical database connection open.
            source_connector.close()

        # --------------------------------------------------------------
        # TARGET VALIDATION
        # --------------------------------------------------------------

        # Retrieve the target connector from the resolved context.
        target_connector = context.target_connector

        # Retrieve the target physical object.
        target_object = context.target_object

        # Connect to the target database.
        target_connection = target_connector.connect()

        try:
            # Validate that the target table already exists.
            #
            # Auto-create-target is currently FALSE in the Customer POC,
            # so the target must already exist.
            target_query = """
                SELECT 1
                FROM information_schema.tables
                WHERE table_catalog = %s
                  AND table_schema = %s
                  AND table_name = %s
                LIMIT 1;
            """

            with target_connection.cursor() as cursor:
                cursor.execute(
                    target_query,
                    (
                        target_connector.metadata.database_name,
                        target_object.schema_name,
                        target_object.object_name,
                    ),
                )

                target_table_exists = cursor.fetchone() is not None

            # The target must exist because auto-create is disabled.
            if not target_table_exists:
                raise LookupError(
                    "Target table was not found: "
                    f"{target_object.catalog_name}."
                    f"{target_object.schema_name}."
                    f"{target_object.object_name}"
                )

            # Record successful target-object validation.
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
            # TARGET COLUMN VALIDATION
            # ----------------------------------------------------------

            # Retrieve target columns in ordinal order.
            target_columns_query = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    ordinal_position
                FROM information_schema.columns
                WHERE table_catalog = %s
                  AND table_schema = %s
                  AND table_name = %s
                ORDER BY ordinal_position;
            """

            with target_connection.cursor() as cursor:
                cursor.execute(
                    target_columns_query,
                    (
                        target_connector.metadata.database_name,
                        target_object.schema_name,
                        target_object.object_name,
                    ),
                )

                target_columns = cursor.fetchall()

            # A target without columns cannot receive data.
            if not target_columns:
                raise LookupError(
                    "Target table contains no columns: "
                    f"{target_object.schema_name}."
                    f"{target_object.object_name}"
                )

            # Convert the result into an ordered column-name list.
            target_column_names = [
                row[0]
                for row in target_columns
            ]

            # The Customer target was created from the same four mapped
            # fields.
            expected_target_columns = [
                "customer_id",
                "customer_name",
                "email",
                "city",
            ]

            # Validate that every required target field exists.
            missing_target_columns = [
                column
                for column in expected_target_columns
                if column not in target_column_names
            ]

            if missing_target_columns:
                raise LookupError(
                    "Required target columns are missing: "
                    f"{missing_target_columns}"
                )

            # Record successful target-column validation.
            results.append(
                ValidationResult(
                    check_name="TARGET_COLUMNS",
                    passed=True,
                    message=(
                        "Required target columns are available: "
                        f"{expected_target_columns}"
                    ),
                )
            )

            # ----------------------------------------------------------
            # COLUMN ORDER VALIDATION
            # ----------------------------------------------------------
            #
            # The current Customer POC uses direct one-to-one mapping.
            #
            # Therefore the source and target columns should appear in the
            # same logical order.
            #
            # Later, the generic mapping engine will use mapping_field
            # metadata instead of relying on physical ordinal order.
            if (
                source_column_names
                != target_column_names
            ):
                raise ValueError(
                    "Source and target column order does not match. "
                    f"Source={source_column_names}, "
                    f"Target={target_column_names}"
                )

            # Record successful column-order validation.
            results.append(
                ValidationResult(
                    check_name="COLUMN_ORDER",
                    passed=True,
                    message=(
                        "Source and target column order matches."
                    ),
                )
            )

        finally:
            # Always close the target connector after validation.
            target_connector.close()

        # --------------------------------------------------------------
        # EXECUTION CONFIGURATION VALIDATION
        # --------------------------------------------------------------

        # Retrieve the resolved mapping configuration.
        mapping = context.execution_plan.mapping

        # Retrieve the resolved load configuration.
        load_config = context.execution_plan.load_config

        # Retrieve the resolved target configuration.
        target_config = context.execution_plan.target_config

        # Validate the current Customer POC load type.
        if mapping.load_type_code != "FULL":
            raise ValueError(
                "Pre-execution validator currently supports "
                f"FULL load only, received: {mapping.load_type_code}"
            )

        # Validate the current Customer POC load strategy.
        if mapping.load_strategy_code != "TRUNCATE_INSERT":
            raise ValueError(
                "Pre-execution validator currently supports "
                "TRUNCATE_INSERT only, received: "
                f"{mapping.load_strategy_code}"
            )

        # Validate the configured batch size.
        if load_config.batch_size <= 0:
            raise ValueError(
                "Batch size must be greater than zero."
            )

        # Validate that the load configuration is active.
        if not load_config.is_active:
            raise ValueError(
                "Load configuration is inactive."
            )

        # Auto-create is disabled for this POC, so the target object must
        # already have been validated above.
        if target_config.auto_create_target:
            raise ValueError(
                "Customer POC expects auto_create_target=False."
            )

        # Record successful execution configuration validation.
        results.append(
            ValidationResult(
                check_name="EXECUTION_CONFIGURATION",
                passed=True,
                message=(
                    "FULL / TRUNCATE_INSERT configuration is valid."
                ),
            )
        )

        # Return every successful validation result.
        return results