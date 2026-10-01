"""
Customer Target Transaction Test
=================================

Purpose
-------
Validate the complete target-side transaction behavior.

Test flow
---------
    BEGIN
      |
      +-- TRUNCATE target
      |
      +-- INSERT 2 test rows
      |
      +-- Verify rows
      |
    ROLLBACK
      |
      +-- Verify original target state is restored

WHY
---
Before building the Full Load Executor, we need to prove that
TRUNCATE, INSERT, COMMIT/ROLLBACK work correctly as one target
transaction.

IMPORTANT
---------
This test intentionally uses ROLLBACK.

No test data will be permanently committed.
"""

from app.runtime.connection_resolver import RuntimeConnectionResolver


def main() -> None:
    """
    Test the target transaction lifecycle.
    """

    print("=" * 70)
    print("CUSTOMER TARGET TRANSACTION TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # Resolve target connector
    # ---------------------------------------------------------

    # Connection ID 11 represents the metadata-defined target
    # PostgreSQL connection.
    connection_resolver = RuntimeConnectionResolver()

    target_connector = connection_resolver.resolve(
        connection_id=11,
    )

    try:
        # -----------------------------------------------------
        # Connect to target
        # -----------------------------------------------------

        target_connector.connect()

        print()
        print("Target Connection : OPEN")

        # -----------------------------------------------------
        # Begin transaction
        # -----------------------------------------------------

        # The PostgreSQL connector validates that an active
        # connection exists.
        target_connector.begin_transaction()

        print("Transaction : BEGIN")

        # -----------------------------------------------------
        # Truncate target
        # -----------------------------------------------------

        # The current full-load strategy is TRUNCATE_INSERT.
        #
        # IMPORTANT:
        # truncate_table() does not commit.
        target_connector.truncate_table(
            target_schema="warehouse",
            target_table="customer_target",
        )

        print("Target TRUNCATE : PASSED")

        # -----------------------------------------------------
        # Prepare temporary test rows
        # -----------------------------------------------------

        test_rows = [
            (
                900001,
                "MDIP Transaction Test 1",
                "transaction-test-1@example.com",
                "Test City",
            ),
            (
                900002,
                "MDIP Transaction Test 2",
                "transaction-test-2@example.com",
                "Test City",
            ),
        ]

        target_columns = [
            "customer_id",
            "customer_name",
            "email",
            "city",
        ]

        # -----------------------------------------------------
        # Insert test batch
        # -----------------------------------------------------

        rows_written = target_connector.write_batch(
            target_schema="warehouse",
            target_table="customer_target",
            column_names=target_columns,
            rows=test_rows,
        )

        print(
            f"Rows Written : {rows_written}"
        )

        # -----------------------------------------------------
        # Verify rows inside transaction
        # -----------------------------------------------------

        # We use the connector-managed connection only for this
        # verification query.
        #
        # This is still inside the same transaction.
        connection = target_connector._require_connection()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM "warehouse"."customer_target"
                WHERE "customer_id" IN (900001, 900002);
                """
            )

            row = cursor.fetchone()

        rows_found = row[0]

        print(
            f"Rows Visible Before Rollback : {rows_found}"
        )

        if rows_found != 2:
            raise RuntimeError(
                "Expected 2 test rows before rollback, "
                f"but found {rows_found}."
            )

        print("Pre-Rollback Verification : PASSED")

        # -----------------------------------------------------
        # Roll back transaction
        # -----------------------------------------------------

        # This should undo BOTH:
        #
        #   1. TRUNCATE
        #   2. INSERT
        #
        # Therefore the original target state should be restored.
        target_connector.rollback()

        print("Transaction ROLLBACK : PASSED")

        # -----------------------------------------------------
        # Verify rollback
        # -----------------------------------------------------

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM "warehouse"."customer_target"
                WHERE "customer_id" IN (900001, 900002);
                """
            )

            row = cursor.fetchone()

        rows_after_rollback = row[0]

        print(
            f"Test Rows After Rollback : "
            f"{rows_after_rollback}"
        )

        if rows_after_rollback != 0:
            raise RuntimeError(
                "Rollback verification failed. "
                "Test rows still exist."
            )

        print("Rollback Verification : PASSED")
        print("Test Data Persisted : NO")

    finally:
        # -----------------------------------------------------
        # Close target connection
        # -----------------------------------------------------

        target_connector.close()

        print("Target Connection : CLOSED")

    print()
    print("=" * 70)
    print("CUSTOMER TARGET TRANSACTION TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()