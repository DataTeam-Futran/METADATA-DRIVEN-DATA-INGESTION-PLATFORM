from app.db.metastore import get_metastore_connection


KEEP_IDS = (1, 2, 3, 4, 5, 6)
DELETE_IDS = (13, 14, 15, 16, 17, 18)
MAPPING_VERSION_ID = 1


def main() -> None:
    print("=" * 80)
    print("DUPLICATE MAPPING FIELD CLEANUP")
    print("=" * 80)

    with get_metastore_connection() as connection:

        try:
            # ---------------------------------------------------------
            # 1. VERIFY ORIGINAL RECORDS
            # ---------------------------------------------------------
            print()
            print("1. VERIFYING ORIGINAL RECORDS")

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mapping_field_id,
                        source_field_name,
                        target_field_name,
                        target_data_type,
                        transformation_type,
                        transformation_expression,
                        is_key,
                        is_required,
                        ordinal_position
                    FROM ingest.mapping_field
                    WHERE mapping_version_id = %s
                      AND mapping_field_id = ANY(%s)
                    ORDER BY ordinal_position;
                    """,
                    (
                        MAPPING_VERSION_ID,
                        list(KEEP_IDS),
                    ),
                )

                keep_rows = cursor.fetchall()

            print(f"Original records found: {len(keep_rows)}")

            if len(keep_rows) != 6:
                raise RuntimeError(
                    "Expected exactly 6 original mapping-field records."
                )

            for row in keep_rows:
                print(
                    f"  KEEP id={row[0]} | "
                    f"{row[1]} -> {row[2]}"
                )

            # ---------------------------------------------------------
            # 2. VERIFY DUPLICATE RECORDS
            # ---------------------------------------------------------
            print()
            print("2. VERIFYING DUPLICATE RECORDS")

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mapping_field_id,
                        source_field_name,
                        target_field_name,
                        target_data_type,
                        transformation_type,
                        transformation_expression,
                        is_key,
                        is_required,
                        ordinal_position
                    FROM ingest.mapping_field
                    WHERE mapping_version_id = %s
                      AND mapping_field_id = ANY(%s)
                    ORDER BY ordinal_position;
                    """,
                    (
                        MAPPING_VERSION_ID,
                        list(DELETE_IDS),
                    ),
                )

                duplicate_rows = cursor.fetchall()

            print(
                f"Duplicate records found: "
                f"{len(duplicate_rows)}"
            )

            if len(duplicate_rows) != 6:
                raise RuntimeError(
                    "Expected exactly 6 duplicate records."
                )

            for row in duplicate_rows:
                print(
                    f"  DELETE id={row[0]} | "
                    f"{row[1]} -> {row[2]}"
                )

            # ---------------------------------------------------------
            # 3. VERIFY EXACT DUPLICATE CONTENT
            # ---------------------------------------------------------
            print()
            print("3. VERIFYING DUPLICATE CONTENT")

            keep_by_position = {
                row[8]: row[1:]
                for row in keep_rows
            }

            duplicate_by_position = {
                row[8]: row[1:]
                for row in duplicate_rows
            }

            if keep_by_position != duplicate_by_position:
                raise RuntimeError(
                    "Duplicate records are not exact matches. "
                    "Cleanup aborted."
                )

            print("All duplicate records match the original records.")

            # ---------------------------------------------------------
            # 4. DELETE DUPLICATES
            # ---------------------------------------------------------
            print()
            print("4. DELETING DUPLICATES")

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM ingest.mapping_field
                    WHERE mapping_version_id = %s
                      AND mapping_field_id = ANY(%s)
                    RETURNING mapping_field_id;
                    """,
                    (
                        MAPPING_VERSION_ID,
                        list(DELETE_IDS),
                    ),
                )

                deleted_rows = cursor.fetchall()

            deleted_ids = [row[0] for row in deleted_rows]

            print(f"Deleted records: {len(deleted_ids)}")
            print(f"Deleted IDs: {deleted_ids}")

            if set(deleted_ids) != set(DELETE_IDS):
                raise RuntimeError(
                    "The deleted IDs do not match the expected "
                    "duplicate IDs. Rolling back."
                )

            # ---------------------------------------------------------
            # 5. VERIFY FINAL STATE
            # ---------------------------------------------------------
            print()
            print("5. VERIFYING FINAL STATE")

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        mapping_field_id,
                        source_field_name,
                        target_field_name,
                        ordinal_position
                    FROM ingest.mapping_field
                    WHERE mapping_version_id = %s
                    ORDER BY ordinal_position;
                    """,
                    (MAPPING_VERSION_ID,),
                )

                final_rows = cursor.fetchall()

            print(
                f"Remaining mapping fields: "
                f"{len(final_rows)}"
            )

            for row in final_rows:
                print(
                    f"  id={row[0]} | "
                    f"{row[1]} -> {row[2]} | "
                    f"position={row[3]}"
                )

            if len(final_rows) != 6:
                raise RuntimeError(
                    "Expected exactly 6 mapping fields after cleanup."
                )

            final_ids = [row[0] for row in final_rows]

            if final_ids != list(KEEP_IDS):
                raise RuntimeError(
                    f"Unexpected final mapping-field IDs: "
                    f"{final_ids}"
                )

            # ---------------------------------------------------------
            # 6. COMMIT
            # ---------------------------------------------------------
            connection.commit()

            print()
            print("TRANSACTION COMMITTED")

        except Exception:
            connection.rollback()

            print()
            print("ERROR DETECTED")
            print("TRANSACTION ROLLED BACK")

            raise

    print()
    print("=" * 80)
    print("DUPLICATE MAPPING FIELD CLEANUP COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()