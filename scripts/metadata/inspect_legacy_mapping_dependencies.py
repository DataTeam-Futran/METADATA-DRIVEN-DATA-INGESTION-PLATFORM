"""
Legacy Mapping Dependency Inspection

Purpose
-------
This script performs a READ-ONLY analysis of the legacy ingest.mapping_* tables.

Why we need this
----------------
We discovered that three legacy tables still reference ingest.mapping_version:

    1. ingest.load_config
    2. ingest.mapping_field
    3. ingest.mapping_source

The new metadata architecture uses map.mapping_version as the source of truth.

Before changing any foreign keys, we must understand:
    - Which legacy mapping versions are actually used.
    - Which rows exist in the legacy child tables.
    - Whether those mapping version IDs also exist in map.mapping_version.
    - Whether Customer mapping version 2 has any legacy representation.

This script does NOT modify metadata.
"""

from app.db.metastore import get_metastore_connection


def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    Why:
    A standard output format makes the dependency analysis
    easier to review during development and troubleshooting.
    """
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def print_query_results(
    connection,
    query: str,
    title: str,
) -> None:
    """
    Execute a read-only query and print the returned rows.

    Why:
    We want this inspection script to be reusable for multiple
    legacy dependency checks without duplicating cursor logic.
    """

    print_section(title)

    with connection.cursor() as cursor:
        cursor.execute(query)

        # Fetch column names so the output remains understandable.
        column_names = [
            description.name
            for description in cursor.description
        ]

        print(" | ".join(column_names))

        rows = cursor.fetchall()

        if not rows:
            print("(NO ROWS)")
            return

        for row in rows:
            print(row)


def main() -> None:
    """
    Run the complete legacy mapping dependency analysis.

    Important:
    This function only performs SELECT statements.
    No INSERT, UPDATE, DELETE, ALTER or DROP statements are used.
    """

    print("=" * 100)
    print("LEGACY MAPPING DEPENDENCY IMPACT ANALYSIS")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Inspect legacy mapping_field rows.
        #
        # Why:
        # mapping_field has a foreign key to ingest.mapping_version.
        # We need to know which legacy mapping versions are actually used.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                mapping_version_id,
                COUNT(*) AS row_count
            FROM ingest.mapping_field
            GROUP BY mapping_version_id
            ORDER BY mapping_version_id;
            """,
            "LEGACY TABLE: ingest.mapping_field",
        )

        # ------------------------------------------------------------------
        # 2. Inspect legacy mapping_source rows.
        #
        # Why:
        # mapping_source also references ingest.mapping_version.
        # This tells us whether legacy source definitions are still present.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                mapping_version_id,
                COUNT(*) AS row_count
            FROM ingest.mapping_source
            GROUP BY mapping_version_id
            ORDER BY mapping_version_id;
            """,
            "LEGACY TABLE: ingest.mapping_source",
        )

        # ------------------------------------------------------------------
        # 3. Inspect legacy load configuration.
        #
        # Why:
        # We already know mapping version 1 is used by load_config.
        # This confirms all legacy load configurations currently present.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                load_config_id,
                mapping_version_id,
                load_type_code,
                batch_size,
                truncate_before_load,
                is_active
            FROM ingest.load_config
            ORDER BY load_config_id;
            """,
            "LEGACY TABLE: ingest.load_config",
        )

        # ------------------------------------------------------------------
        # 4. Compare legacy mapping version IDs with new mapping version IDs.
        #
        # Why:
        # This identifies whether the existing legacy child records can
        # safely be pointed to the new map.mapping_version table.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                lm.mapping_version_id,
                lm.mapping_id,
                lm.version_number,
                lm.status AS legacy_status,
                CASE
                    WHEN nm.mapping_version_id IS NOT NULL
                    THEN 'EXISTS_IN_NEW_MODEL'
                    ELSE 'NOT_IN_NEW_MODEL'
                END AS new_model_status,
                nm.tenant_id,
                nm.mapping_id AS new_mapping_id,
                nm.version_no AS new_version_no,
                nm.status_code AS new_status
            FROM ingest.mapping_version lm
            LEFT JOIN map.mapping_version nm
                ON nm.mapping_version_id = lm.mapping_version_id
            ORDER BY lm.mapping_version_id;
            """,
            "LEGACY VS NEW MAPPING VERSION COMPARISON",
        )

        # ------------------------------------------------------------------
        # 5. Specifically check mapping version 1.
        #
        # Why:
        # Existing ingest.load_config uses mapping_version_id = 1.
        # Before changing its FK, we must confirm that map.mapping_version
        # ID 1 represents the same logical mapping.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                'LEGACY' AS model,
                mapping_version_id,
                mapping_id,
                version_number,
                status,
                config_hash
            FROM ingest.mapping_version
            WHERE mapping_version_id = 1

            UNION ALL

            SELECT
                'NEW' AS model,
                mapping_version_id,
                mapping_id,
                version_no AS version_number,
                status_code AS status,
                config_hash
            FROM map.mapping_version
            WHERE mapping_version_id = 1

            ORDER BY model;
            """,
            "MAPPING VERSION ID 1 COMPARISON",
        )

        # ------------------------------------------------------------------
        # 6. Specifically check Customer mapping version 2.
        #
        # Why:
        # Customer mapping version 2 exists only in the new model.
        # This confirms that it is ready to become the authoritative
        # mapping version for execution configuration.
        # ------------------------------------------------------------------
        print_query_results(
            connection,
            """
            SELECT
                mapping_version_id,
                tenant_id,
                mapping_id,
                version_no,
                primary_source_dataset_id,
                primary_source_schema_version_id,
                target_dataset_id,
                target_schema_version_id,
                datatype_mapping_set_id,
                load_type_code,
                load_strategy_code,
                status_code,
                config_hash
            FROM map.mapping_version
            WHERE mapping_version_id = 2;
            """,
            "CUSTOMER MAPPING VERSION 2",
        )

    print()
    print("=" * 100)
    print("LEGACY MAPPING DEPENDENCY ANALYSIS COMPLETED")
    print("Operation         : READ ONLY")
    print("Metadata modified : NO")
    print("=" * 100)


if __name__ == "__main__":
    """
    Execute the inspection when this module is run directly.
    """
    main()