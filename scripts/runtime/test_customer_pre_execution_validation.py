"""
Customer Pre-Execution Validation Test

Purpose
-------
Validates the physical source and target environment before the first
Customer full-load execution.

This test:

    - resolves the runtime execution context
    - opens source connection
    - validates source table
    - validates source columns
    - closes source connection
    - opens target connection
    - validates target table
    - validates target columns
    - closes target connection
    - validates execution configuration

This test does NOT:

    - truncate the target
    - insert data
    - update data
    - delete data
    - modify metadata
"""

# Import the runtime context resolver that creates the complete execution
# context.
from app.runtime.context_resolver import RuntimeExecutionContextResolver

# Import the pre-execution validator.
from app.runtime.pre_execution_validator import PreExecutionValidator


def main() -> None:
    """
    Execute the Customer pre-execution validation test.
    """

    # Customer POC metadata identifiers.
    tenant_id = 1
    pipeline_version_id = 2
    environment_id = 1

    print("=" * 100)
    print("CUSTOMER PRE-EXECUTION VALIDATION")
    print("=" * 100)

    # ----------------------------------------------------------------------
    # STEP 1 - BUILD RUNTIME EXECUTION CONTEXT
    # ----------------------------------------------------------------------
    # The context resolver resolves:
    #
    #     Pipeline Version
    #         ↓
    #     Mapping
    #         ↓
    #     Load Configuration
    #         ↓
    #     Source Object
    #         ↓
    #     Target Object
    #         ↓
    #     Source Connector
    #         ↓
    #     Target Connector
    #
    # No physical connection is opened during this resolution step.
    context_resolver = RuntimeExecutionContextResolver()

    context = context_resolver.resolve(
        pipeline_version_id=pipeline_version_id,
        tenant_id=tenant_id,
        environment_id=environment_id,
    )

    print()
    print("RUNTIME CONTEXT")
    print("-" * 100)

    print(
        f"Pipeline Version ID     : "
        f"{context.execution_plan.pipeline_version_id}"
    )

    print(
        f"Pipeline Code           : "
        f"{context.execution_plan.pipeline_code}"
    )

    print(
        f"Source                  : "
        f"{context.source_object.catalog_name}."
        f"{context.source_object.schema_name}."
        f"{context.source_object.object_name}"
    )

    print(
        f"Target                  : "
        f"{context.target_object.catalog_name}."
        f"{context.target_object.schema_name}."
        f"{context.target_object.object_name}"
    )

    # ----------------------------------------------------------------------
    # STEP 2 - RUN PHYSICAL PRE-EXECUTION VALIDATION
    # ----------------------------------------------------------------------
    # The validator opens the physical connections only for read-only
    # validation and closes them afterward.
    validator = PreExecutionValidator()

    validation_results = validator.validate(context)

    # ----------------------------------------------------------------------
    # STEP 3 - DISPLAY VALIDATION RESULTS
    # ----------------------------------------------------------------------
    print()
    print("VALIDATION RESULTS")
    print("-" * 100)

    # Display each individual validation result.
    for result in validation_results:
        print(
            f"[{'PASSED' if result.passed else 'FAILED'}] "
            f"{result.check_name}"
        )
        print(
            f"        {result.message}"
        )

    # ----------------------------------------------------------------------
    # STEP 4 - FINAL VALIDATION
    # ----------------------------------------------------------------------
    # The test should only pass when every validation result is successful.
    failed_results = [
        result
        for result in validation_results
        if not result.passed
    ]

    # If any validation failed, explicitly fail the test.
    if failed_results:
        raise AssertionError(
            "Pre-execution validation failed: "
            f"{failed_results}"
        )

    # ----------------------------------------------------------------------
    # FINAL RESULT
    # ----------------------------------------------------------------------
    print()
    print("=" * 100)
    print("CUSTOMER PRE-EXECUTION VALIDATION PASSED")
    print("=" * 100)

    print(
        "Source                   : "
        "demo_source_db.public.customer"
    )

    print(
        "Target                   : "
        "ingestion_metastore.warehouse.customer_target"
    )

    print()
    print("Source Connection       : VALIDATED")
    print("Target Connection       : VALIDATED")
    print("Source Object           : VALIDATED")
    print("Target Object           : VALIDATED")
    print("Source Columns          : VALIDATED")
    print("Target Columns          : VALIDATED")
    print("Execution Configuration : VALIDATED")

    # Explicitly state that this validation did not perform any data
    # modification.
    print()
    print("Target Truncate         : NOT PERFORMED")
    print("Data Read               : NOT PERFORMED")
    print("Data Write              : NOT PERFORMED")
    print("Metadata Modified       : NO")
    print("Operation               : READ ONLY VALIDATION")

    print("=" * 100)


if __name__ == "__main__":
    # Run the validation test when the module is executed directly.
    main()