"""
Inspect Existing Catalog and Datatype Records
==============================================

Purpose:
    Inspect the actual records referenced by the existing Employee
    mapping version.

Why:
    We have already discovered the foreign-key architecture. Now we need
    to understand the real metadata records before creating the Customer
    metadata.

    This script is READ-ONLY.

    It does not insert, update, or delete anything.
"""

from __future__ import annotations

from typing import Any

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Existing mapping references
# ---------------------------------------------------------------------------
# These IDs were resolved from map.mapping_version ID 1.
#
# They are used only for inspection.
MAPPING_VERSION_ID = 1


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def print_section(title: str) -> None:
    """Print a readable section heading."""

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ---------------------------------------------------------------------------
# Generic query printer
# ---------------------------------------------------------------------------
def execute_and_print(
    connection: Any,
    title: str,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> list[tuple[Any, ...]]:
    """
    Execute a read-only query and print the returned rows.

    Why:
        Keeps the inspection code simple while ensuring every query
        produces consistent output.
    """

    print_section(title)

    with connection.cursor() as cursor:
        cursor.execute(query, parameters)

        rows = cursor.fetchall()

        # Retrieve column names from the cursor metadata.
        columns = [
            description.name
            for description in cursor.description
        ]

    if not rows:
        print("No rows found.")
        return []

    print(" | ".join(columns))
    print("-" * 100)

    for row in rows:
        print(
            " | ".join(
                "NULL" if value is None else str(value)
                for value in row
            )
        )

    print()
    print(f"Rows returned: {len(rows)}")

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Inspect the catalog and datatype records referenced by mapping version 1.
    """

    print_section(
        "EXISTING CATALOG AND DATATYPE RECORD INSPECTION"
    )

    print(
        f"Reference Mapping Version ID: {MAPPING_VERSION_ID}"
    )

    with get_metastore_connection() as connection:

        # ================================================================
        # 1. Resolve mapping_version references
        # ================================================================
        mapping_rows = execute_and_print(
            connection=connection,
            title="MAPPING VERSION REFERENCES",
            query="""
                SELECT
                    mapping_version_id,
                    primary_source_dataset_id,
                    primary_source_schema_version_id,
                    target_dataset_id,
                    target_schema_version_id,
                    datatype_mapping_set_id
                FROM map.mapping_version
                WHERE mapping_version_id = %s;
            """,
            parameters=(MAPPING_VERSION_ID,),
        )

        if not mapping_rows:
            print(
                "Mapping version does not exist."
            )
            return

        (
            mapping_version_id,
            source_dataset_id,
            source_schema_version_id,
            target_dataset_id,
            target_schema_version_id,
            datatype_mapping_set_id,
        ) = mapping_rows[0]

        # ================================================================
        # 2. Inspect source dataset
        # ================================================================
        execute_and_print(
            connection=connection,
            title="SOURCE DATASET",
            query="""
                SELECT
                    *
                FROM catalog.dataset
                WHERE dataset_id = %s;
            """,
            parameters=(source_dataset_id,),
        )

        # ================================================================
        # 3. Inspect target dataset
        # ================================================================
        execute_and_print(
            connection=connection,
            title="TARGET DATASET",
            query="""
                SELECT
                    *
                FROM catalog.dataset
                WHERE dataset_id = %s;
            """,
            parameters=(target_dataset_id,),
        )

        # ================================================================
        # 4. Inspect source dataset binding
        # ================================================================
        execute_and_print(
            connection=connection,
            title="SOURCE DATASET BINDING",
            query="""
                SELECT
                    *
                FROM catalog.dataset_binding
                WHERE dataset_id = %s
                ORDER BY dataset_binding_id;
            """,
            parameters=(source_dataset_id,),
        )

        # ================================================================
        # 5. Inspect target dataset binding
        # ================================================================
        execute_and_print(
            connection=connection,
            title="TARGET DATASET BINDING",
            query="""
                SELECT
                    *
                FROM catalog.dataset_binding
                WHERE dataset_id = %s
                ORDER BY dataset_binding_id;
            """,
            parameters=(target_dataset_id,),
        )

        # ================================================================
        # 6. Inspect source schema version
        # ================================================================
        execute_and_print(
            connection=connection,
            title="SOURCE SCHEMA VERSION",
            query="""
                SELECT
                    *
                FROM catalog.dataset_schema_version
                WHERE schema_version_id = %s;
            """,
            parameters=(source_schema_version_id,),
        )

        # ================================================================
        # 7. Inspect target schema version
        # ================================================================
        execute_and_print(
            connection=connection,
            title="TARGET SCHEMA VERSION",
            query="""
                SELECT
                    *
                FROM catalog.dataset_schema_version
                WHERE schema_version_id = %s;
            """,
            parameters=(target_schema_version_id,),
        )

        # ================================================================
        # 8. Inspect source fields
        # ================================================================
        execute_and_print(
            connection=connection,
            title="SOURCE DATASET FIELDS",
            query="""
                SELECT
                    *
                FROM catalog.dataset_field
                WHERE schema_version_id = %s
                ORDER BY ordinal_no;
            """,
            parameters=(source_schema_version_id,),
        )

        # ================================================================
        # 9. Inspect target fields
        # ================================================================
        execute_and_print(
            connection=connection,
            title="TARGET DATASET FIELDS",
            query="""
                SELECT
                    *
                FROM catalog.dataset_field
                WHERE schema_version_id = %s
                ORDER BY ordinal_no;
            """,
            parameters=(target_schema_version_id,),
        )

        # ================================================================
        # 10. Inspect datatype mapping set
        # ================================================================
        execute_and_print(
            connection=connection,
            title="DATATYPE MAPPING SET",
            query="""
                SELECT
                    *
                FROM dtype.datatype_mapping_set
                WHERE mapping_set_id = %s;
            """,
            parameters=(datatype_mapping_set_id,),
        )

        # ================================================================
        # 11. Inspect datatype mapping rules
        # ================================================================
        execute_and_print(
            connection=connection,
            title="DATATYPE MAPPING RULES",
            query="""
                SELECT
                    *
                FROM dtype.datatype_mapping_rule
                WHERE mapping_set_id = %s
                ORDER BY priority_no, mapping_rule_id;
            """,
            parameters=(datatype_mapping_set_id,),
        )

        # ================================================================
        # 12. Inspect native datatypes used by source fields
        # ================================================================
        execute_and_print(
            connection=connection,
            title="SOURCE NATIVE DATATYPES",
            query="""
                SELECT DISTINCT
                    nd.*
                FROM catalog.dataset_field AS df
                JOIN dtype.native_datatype AS nd
                    ON nd.native_datatype_id = df.native_datatype_id
                WHERE df.schema_version_id = %s
                ORDER BY nd.native_datatype_id;
            """,
            parameters=(source_schema_version_id,),
        )

        # ================================================================
        # 13. Inspect native datatypes used by target fields
        # ================================================================
        execute_and_print(
            connection=connection,
            title="TARGET NATIVE DATATYPES",
            query="""
                SELECT DISTINCT
                    nd.*
                FROM catalog.dataset_field AS df
                JOIN dtype.native_datatype AS nd
                    ON nd.native_datatype_id = df.native_datatype_id
                WHERE df.schema_version_id = %s
                ORDER BY nd.native_datatype_id;
            """,
            parameters=(target_schema_version_id,),
        )

        # ================================================================
        # 14. Final summary
        # ================================================================
        print_section(
            "INSPECTION COMPLETE"
        )

        print(
            "The existing Employee catalog and datatype records were "
            "read successfully."
        )

        print(
            "No metadata was inserted, updated, or deleted."
        )


# ---------------------------------------------------------------------------
# Python entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()