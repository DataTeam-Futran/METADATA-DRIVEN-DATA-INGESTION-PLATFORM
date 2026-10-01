"""
Customer Catalog Registration Check
====================================

Purpose:
    Check whether the Customer source dataset is already registered in the
    production-style catalog for the confirmed Tenant 1 / Project 1 context.

Confirmed execution context:
    Tenant      : 1
    Project     : 1
    Environment : 1
    Source      : Connection 1
    Target      : Connection 11

Why this check is required:
    We already found a CUSTOMER_DATASET under another tenant/project.
    That record belongs to tenant 2 / project 3 and therefore must not be
    reused for this POC.

    Before creating a new catalog.dataset record, we check whether the
    correct Tenant 1 / Project 1 registration already exists.

Important:
    This script is READ-ONLY.
    It does not INSERT, UPDATE, or DELETE any metadata.
"""

from __future__ import annotations

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Check Customer dataset registration and any existing bindings.

    The query intentionally filters by tenant and project so that a
    similarly named dataset belonging to another tenant does not affect
    the current POC.
    """

    # These values were confirmed from the previous security-context
    # inspection. They are not guessed.
    tenant_id = 1
    project_id = 1

    print("=" * 100)
    print("CUSTOMER CATALOG REGISTRATION CHECK")
    print("=" * 100)

    with get_metastore_connection() as connection:

        # ------------------------------------------------------------------
        # 1. Check for CUSTOMER_DATASET in the confirmed tenant/project.
        # ------------------------------------------------------------------
        # We use dataset_code rather than dataset_name because the code is
        # intended to be the stable metadata identifier.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_id,
                    tenant_id,
                    project_id,
                    dataset_code,
                    dataset_name,
                    object_type_code,
                    dataset_role_code,
                    layer_code,
                    status_code
                FROM catalog.dataset
                WHERE tenant_id = %s
                  AND project_id = %s
                  AND dataset_code = %s
                ORDER BY dataset_id;
                """,
                (
                    tenant_id,
                    project_id,
                    "CUSTOMER_DATASET",
                ),
            )

            dataset_rows = cursor.fetchall()

        print("\n" + "=" * 100)
        print("CUSTOMER DATASET IN TENANT 1 / PROJECT 1")
        print("=" * 100)

        if not dataset_rows:
            print("No CUSTOMER_DATASET found.")
        else:
            print(
                "dataset_id | tenant_id | project_id | dataset_code | "
                "dataset_name | object_type_code | dataset_role_code | "
                "layer_code | status_code"
            )
            print("-" * 100)

            for row in dataset_rows:
                print(" | ".join(str(value) for value in row))

        # ------------------------------------------------------------------
        # 2. Check all Customer dataset registrations globally.
        # ------------------------------------------------------------------
        # This is useful because we already know another tenant contains
        # CUSTOMER_DATASET. We want to clearly distinguish that record from
        # our Tenant 1 / Project 1 registration.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    dataset_id,
                    tenant_id,
                    project_id,
                    dataset_code,
                    dataset_name,
                    dataset_role_code,
                    status_code
                FROM catalog.dataset
                WHERE dataset_code = %s
                ORDER BY tenant_id, project_id, dataset_id;
                """,
                ("CUSTOMER_DATASET",),
            )

            all_customer_rows = cursor.fetchall()

        print("\n" + "=" * 100)
        print("ALL CUSTOMER_DATASET REGISTRATIONS")
        print("=" * 100)

        if not all_customer_rows:
            print("No CUSTOMER_DATASET registrations found.")
        else:
            print(
                "dataset_id | tenant_id | project_id | dataset_code | "
                "dataset_name | dataset_role_code | status_code"
            )
            print("-" * 100)

            for row in all_customer_rows:
                print(" | ".join(str(value) for value in row))

        # ------------------------------------------------------------------
        # 3. Check bindings for any matching dataset.
        # ------------------------------------------------------------------
        # A dataset may already have a physical source binding. We therefore
        # inspect bindings before creating a new one.
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    d.dataset_id,
                    d.tenant_id,
                    d.project_id,
                    d.dataset_code,
                    b.dataset_binding_id,
                    b.environment_id,
                    b.connection_id,
                    b.catalog_name,
                    b.schema_name,
                    b.object_name,
                    b.status_code
                FROM catalog.dataset AS d
                LEFT JOIN catalog.dataset_binding AS b
                    ON b.dataset_id = d.dataset_id
                WHERE d.dataset_code = %s
                ORDER BY
                    d.tenant_id,
                    d.project_id,
                    d.dataset_id,
                    b.dataset_binding_id;
                """,
                ("CUSTOMER_DATASET",),
            )

            binding_rows = cursor.fetchall()

        print("\n" + "=" * 100)
        print("CUSTOMER DATASET BINDINGS")
        print("=" * 100)

        if not binding_rows:
            print("No Customer dataset bindings found.")
        else:
            print(
                "dataset_id | tenant_id | project_id | dataset_code | "
                "binding_id | environment_id | connection_id | "
                "catalog_name | schema_name | object_name | status_code"
            )
            print("-" * 100)

            for row in binding_rows:
                print(" | ".join(str(value) for value in row))

    # ----------------------------------------------------------------------
    # Completion
    # ----------------------------------------------------------------------
    # This script contains only SELECT statements, so no metadata is
    # modified and no commit is required.
    print("\n" + "=" * 100)
    print("CHECK COMPLETE")
    print("=" * 100)
    print("No metadata was modified.")


if __name__ == "__main__":
    # Execute the read-only catalog registration check when this file is
    # executed as a Python module.
    main()