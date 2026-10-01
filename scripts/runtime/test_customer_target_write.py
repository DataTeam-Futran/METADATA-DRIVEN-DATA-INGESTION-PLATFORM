"""
Customer Target Write Test
===========================

Purpose
-------
Test the PostgreSQL connector's write_batch() method.

This test inserts two temporary records into:

    ingestion_metastore.warehouse.customer_target

and then rolls the transaction back.

WHY?
----
We want to prove that the connector can write data before
building the complete Full Load execution engine.

The test must NOT permanently modify the target table.
"""

from app.runtime.connection_resolver import RuntimeConnectionResolver


def main() -> None:
    """
    Test PostgreSQL target batch writing.
    """

    print("=" * 70)
    print("CUSTOMER TARGET WRITE TEST")
    print("=" * 70)

    # ---------------------------------------------------------
    # Resolve target connector
    # ---------------------------------------------------------

    # Connection ID 11 is the metadata-defined target connection.
    connection_resolver = RuntimeConnectionResolver()

    target_connector = connection_resolver.resolve(
        connection_id=11,
    )

    print()
    print(
        f"Target Connector : "
        f"{type(target_connector).__name__}"
    )

    try:
        # -----------------------------------------------------
        # Open target connection
        # -----------------------------------------------------

        # The connector resolves the credential internally and
        # establishes the physical PostgreSQL connection.
        connection = target_connector.connect()

        print("Target Connection : OPEN")

        # -----------------------------------------------------
        # Prepare temporary test rows
        # -----------------------------------------------------

        # These are artificial test records.
        #
        # They are NOT source customer records.
        #
        # We will roll them back after the INSERT test.
        test_rows = [
            (
                900001,
                "MDIP Connector Test 1",
                "mdip-test-1@example.com",
                "Test City",
            ),
            (
                900002,
                "MDIP Connector Test 2",
                "mdip-test-2@example.com",
                "Test City",
            ),
        ]

        # Target columns are explicitly specified so that
        # values are inserted into the correct columns.
        target_columns = [
            "customer_id",
            "customer_name",
            "email",
            "city",
        ]

        # -----------------------------------------------------
        # Write test batch
        # -----------------------------------------------------

        # write_batch() performs the INSERT but intentionally
        # does not commit the transaction.
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
        # Validate expected row count
        # -----------------------------------------------------

        if rows_written != len(test_rows):
            raise RuntimeError(
                "Unexpected number of rows reported "
                "by write_batch()."
            )

        print("Batch Write : PASSED")

        # -----------------------------------------------------
        # Roll back test transaction
        # -----------------------------------------------------

        # The write_batch() method intentionally does not commit.
        #
        # Therefore the temporary records can be removed by
        # rolling back the current target transaction.
        connection.rollback()

        print("Transaction Rollback : PASSED")
        print("Test Data Persisted : NO")

    finally:
        # -----------------------------------------------------
        # Close target connection
        # -----------------------------------------------------

        # Always release the physical database connection,
        # including when the test fails.
        target_connector.close()

        print("Target Connection : CLOSED")

    print()
    print("=" * 70)
    print("CUSTOMER TARGET WRITE TEST PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()