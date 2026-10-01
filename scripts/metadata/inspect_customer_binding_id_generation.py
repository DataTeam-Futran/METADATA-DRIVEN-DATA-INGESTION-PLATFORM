"""
Customer Dataset Binding ID Generation Inspection
===================================================

Purpose:
    Determine how catalog.dataset_binding.dataset_binding_id is generated.

Why this is required:
    dataset_binding_id is a mandatory BIGINT column and the previous
    information_schema inspection showed no column default.

    We must determine whether PostgreSQL manages this value through an
    identity column or sequence before creating the binding.

Important:
    This script is READ-ONLY.
    No INSERT, UPDATE, or DELETE operation is performed.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


def print_rows(
    title: str,
    columns: list[str],
    rows: list[tuple],
) -> None:
    """
    Print database inspection results in a consistent table format.

    A reusable helper keeps the main inspection logic focused on the
    metadata being inspected rather than output formatting.
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
    Inspect PostgreSQL ID generation for dataset_binding_id.
    """

    print("=" * 110)
    print("CUSTOMER DATASET BINDING ID GENERATION INSPECTION")
    print("=" * 110)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Inspect identity information
        # ------------------------------------------------------------------
        # information_schema identifies whether dataset_binding_id is an
        # IDENTITY column and, if so, how PostgreSQL generates the value.
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
                    "dataset_binding",
                    "dataset_binding_id",
                ),
            )

            identity_rows = cursor.fetchall()

        print_rows(
            "DATASET_BINDING_ID IDENTITY INFORMATION",
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
        # 2. Find an associated PostgreSQL sequence
        # ------------------------------------------------------------------
        # pg_get_serial_sequence() detects a sequence associated with the
        # specified table column.
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
                    "catalog.dataset_binding",
                    "dataset_binding_id",
                ),
            )

            sequence_rows = cursor.fetchall()

        print_rows(
            "DATASET_BINDING_ID SEQUENCE",
            [
                "sequence_name",
            ],
            sequence_rows,
        )

        # ------------------------------------------------------------------
        # 3. Inspect PostgreSQL system catalog information
        # ------------------------------------------------------------------
        # pg_attribute and pg_attrdef provide low-level PostgreSQL metadata
        # about identity and generated/default expressions.
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
                    "catalog.dataset_binding",
                    "dataset_binding_id",
                ),
            )

            catalog_rows = cursor.fetchall()

        print_rows(
            "POSTGRESQL CATALOG INFORMATION FOR DATASET_BINDING_ID",
            [
                "column_name",
                "identity_type",
                "generated_type",
                "default_expression",
            ],
            catalog_rows,
        )

        # ------------------------------------------------------------------
        # 4. Inspect existing binding IDs
        # ------------------------------------------------------------------
        # This is informational only. We do not calculate a new ID using
        # MAX(dataset_binding_id) + 1 because that is unsafe for concurrent
        # metadata operations.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_binding_id,
                    tenant_id,
                    dataset_id,
                    environment_id,
                    connection_id,
                    object_name
                FROM catalog.dataset_binding
                ORDER BY dataset_binding_id;
                """
            )

            binding_rows = cursor.fetchall()

        print_rows(
            "EXISTING DATASET BINDING IDS",
            [
                "dataset_binding_id",
                "tenant_id",
                "dataset_id",
                "environment_id",
                "connection_id",
                "object_name",
            ],
            binding_rows,
        )

    # ----------------------------------------------------------------------
    # Completion
    # ----------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("INSPECTION COMPLETE")
    print("=" * 110)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Run the inspection when this module is executed directly.
    main()