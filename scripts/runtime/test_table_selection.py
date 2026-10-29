
from app.runtime.pipeline_orchestrator import PipelineOrchestrator


def main() -> None:
    match = PipelineOrchestrator._table_name_matches

    # Test 1: Table name only
    assert match(
        {"customer"},
        "demo_source_db",
        "public",
        "customer",
    )

    # Test 2: Schema and table
    assert match(
        {"public.customer"},
        "demo_source_db",
        "public",
        "customer",
    )

    # Test 3: Catalog, schema, and table
    assert match(
        {"demo_source_db.public.customer"},
        "demo_source_db",
        "public",
        "customer",
    )

    # Test 4: Matching is case-insensitive
    assert match(
        {"DEMO_SOURCE_DB.PUBLIC.CUSTOMER"},
        "demo_source_db",
        "public",
        "customer",
    )

    # Test 5: An unrelated table must not match
    assert not match(
        {"orders"},
        "demo_source_db",
        "public",
        "customer",
    )

    # Test 6: Partial names must not match
    assert not match(
        {"customer_archive"},
        "demo_source_db",
        "public",
        "customer",
    )

    print("All 6 table-selection tests passed.")


if __name__ == "__main__":
    main()
