
"""Metadata-driven target batch-write rollback integration test."""

from target_write_test_helpers import (
    build_test_rows,
    inspect_writable_columns,
    resolve_target,
    verify_marker_count,
)


def main():
    print("=" * 70)
    print("METADATA-DRIVEN TARGET WRITE TEST")
    print("=" * 70)

    connector, target_object = resolve_target()
    connection = None
    rollback_verified = False

    try:
        connection = connector.connect()

        print(f"Target connector : {type(connector).__name__}")
        print(
            f"Target object    : {target_object.catalog_name}."
            f"{target_object.schema_name}.{target_object.object_name}"
        )

        columns, marker_column = inspect_writable_columns(
            connection, target_object
        )
        column_names = [column["name"] for column in columns]

        marker_values, test_rows = build_test_rows(
            connection, target_object, columns, marker_column
        )

        print(f"Discovered columns: {column_names}")

        rows_written = connector.write_batch(
            target_schema=target_object.schema_name,
            target_table=target_object.object_name,
            column_names=column_names,
            rows=test_rows,
        )

        if rows_written != len(test_rows):
            raise RuntimeError(
                f"Expected {len(test_rows)} inserted rows; "
                f"connector reported {rows_written}."
            )

        visible_before_rollback = verify_marker_count(
            connection, target_object, marker_column, marker_values
        )
        if visible_before_rollback != len(test_rows):
            raise RuntimeError(
                "Inserted test rows could not be verified inside "
                "the transaction."
            )

        print("Batch write verification: PASSED")

        connector.rollback()
        rollback_verified = True

        visible_after_rollback = verify_marker_count(
            connection, target_object, marker_column, marker_values
        )
        if visible_after_rollback != 0:
            raise RuntimeError(
                "Temporary test records remain visible after rollback."
            )

        print("Rollback verification  : PASSED")
        print("Test rows persisted    : NO")


    finally:
        try:
            if connection is not None and not rollback_verified:
                try:
                    connector.rollback()
                    print("Cleanup rollback       : COMPLETED")
                except Exception as exc:
                    print(f"CRITICAL: rollback failed: {exc}")
                    raise
        finally:
            connector.close()
            print("Target connection      : CLOSED")



if __name__ == "__main__":
    main()
