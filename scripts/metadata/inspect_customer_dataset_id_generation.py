"""
Customer Dataset ID Generation Inspection
===========================================

Purpose:
    Determine how catalog.dataset.dataset_id is expected to be generated.

Why this is required:
    catalog.dataset.dataset_id is a mandatory BIGINT column, but the
    information_schema inspection showed that it has no column default.

    We must not guess the next dataset_id using MAX(dataset_id) + 1 because
    that approach is unsafe when multiple processes can insert metadata
    concurrently.

This script checks:
    1. PostgreSQL identity information.
    2. PostgreSQL sequence dependency.
    3. PostgreSQL table definition through pg_catalog.
    4. Existing dataset IDs.

Important:
    This script is READ-ONLY.
    No metadata is inserted, updated, or deleted.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


def print_rows(
    title: str,
    columns: list[str],
    rows: list[tuple],
) -> None:
    """
    Print query results using a consistent tabular format.

    Keeping output formatting in one helper makes the inspection sections
    easier to read and maintain.
    """

    print("\n" + "=" * 110)
    print(title)
    print("=" * 110)

    if not rows:
        print("No rows returned.")
        return

    print(" | ".join(columns))
    print("-" * 110)

    for row in rows:
        print(" | ".join(str(value) for value in row))

    print(f"\nRows returned: {len(rows)}")


def main() -> None:
    """
    Inspect how catalog.dataset.dataset_id is generated.

    The result will determine the safest way to create the first
    CUSTOMER_DATASET record.
    """

    print("=" * 110)
    print("CUSTOMER DATASET ID GENERATION INSPECTION")
    print("=" * 110)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Check information_schema identity metadata
        # ------------------------------------------------------------------
        # PostgreSQL exposes identity-column information through
        # information_schema.columns.
        #
        # If dataset_id is an identity column, this query will show the
        # corresponding identity generation strategy.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    is_identity,
                    identity_generation,
                    identity_start,
                    identity_increment,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                  AND column_name = %s;
                """,
                (
                    "catalog",
                    "dataset",
                    "dataset_id",
                ),
            )

            identity_rows = cursor.fetchall()

        print_rows(
            "DATASET_ID IDENTITY INFORMATION",
            [
                "column_name",
                "data_type",
                "is_identity",
                "identity_generation",
                "identity_start",
                "identity_increment",
                "column_default",
            ],
            identity_rows,
        )

        # ------------------------------------------------------------------
        # 2. Find a sequence dependency
        # ------------------------------------------------------------------
        # pg_get_serial_sequence() returns the sequence associated with a
        # SERIAL/identity-style column when one exists.
        #
        # A NULL result means PostgreSQL has no sequence associated with this
        # column.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    pg_get_serial_sequence(
                        %s,
                        %s
                    ) AS sequence_name;
                """,
                (
                    "catalog.dataset",
                    "dataset_id",
                ),
            )

            sequence_rows = cursor.fetchall()

        print_rows(
            "DATASET_ID SEQUENCE",
            [
                "sequence_name",
            ],
            sequence_rows,
        )

        # ------------------------------------------------------------------
        # 3. Inspect PostgreSQL catalog information
        # ------------------------------------------------------------------
        # pg_attribute and pg_attrdef allow us to verify whether PostgreSQL
        # has an internal default expression associated with dataset_id.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.attname AS column_name,
                    a.attidentity AS identity_type,
                    a.attgenerated AS generated_type,
                    pg_get_expr(ad.adbin, ad.adrelid) AS default_expression
                FROM pg_catalog.pg_attribute AS a
                LEFT JOIN pg_catalog.pg_attrdef AS ad
                    ON ad.adrelid = a.attrelid
                   AND ad.adnum = a.attnum
                WHERE a.attrelid = %s::regclass
                  AND a.attname = %s
                  AND a.attnum > 0
                  AND NOT a.attisdropped;
                """,
                (
                    "catalog.dataset",
                    "dataset_id",
                ),
            )

            catalog_rows = cursor.fetchall()

        print_rows(
            "POSTGRESQL CATALOG INFORMATION FOR DATASET_ID",
            [
                "column_name",
                "identity_type",
                "generated_type",
                "default_expression",
            ],
            catalog_rows,
        )

        # ------------------------------------------------------------------
        # 4. Show existing dataset IDs
        # ------------------------------------------------------------------
        # This is informational only. We do NOT use MAX(dataset_id) + 1 for
        # the INSERT because that would introduce a concurrency problem.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_id,
                    tenant_id,
                    project_id,
                    dataset_code
                FROM catalog.dataset
                ORDER BY dataset_id;
                """
            )

            dataset_rows = cursor.fetchall()

        print_rows(
            "EXISTING DATASET IDS",
            [
                "dataset_id",
                "tenant_id",
                "project_id",
                "dataset_code",
            ],
            dataset_rows,
        )

    # ----------------------------------------------------------------------
    # Completion
    # ----------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("INSPECTION COMPLETE")
    print("=" * 110)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Execute the read-only inspection when the module is run directly.
    main()