from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("DUPLICATE MAPPING FIELD INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            # ---------------------------------------------------------
            # 1. DUPLICATE MAPPING FIELDS
            # ---------------------------------------------------------
            print()
            print("1. MAPPING FIELD RECORDS")

            cursor.execute(
                """
                SELECT
                    mapping_field_id,
                    mapping_version_id,
                    source_field_name,
                    target_field_name,
                    target_data_type,
                    transformation_type,
                    transformation_expression,
                    is_key,
                    is_required,
                    ordinal_position
                FROM ingest.mapping_field
                WHERE mapping_version_id = 1
                ORDER BY ordinal_position, mapping_field_id;
                """
            )

            rows = cursor.fetchall()

            for row in rows:
                print(
                    f"id={row[0]} | "
                    f"version={row[1]} | "
                    f"source={row[2]} | "
                    f"target={row[3]} | "
                    f"type={row[4]} | "
                    f"transform={row[5]} | "
                    f"expression={row[6]} | "
                    f"key={row[7]} | "
                    f"required={row[8]} | "
                    f"position={row[9]}"
                )

            # ---------------------------------------------------------
            # 2. PRIMARY KEY
            # ---------------------------------------------------------
            print()
            print("2. PRIMARY KEY / CONSTRAINT")

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                   AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = 'ingest'
                  AND tc.table_name = 'mapping_field'
                ORDER BY tc.constraint_name, kcu.ordinal_position;
                """
            )

            rows = cursor.fetchall()

            for row in rows:
                print(
                    f"constraint={row[0]} | "
                    f"type={row[1]} | "
                    f"column={row[2]}"
                )

            # ---------------------------------------------------------
            # 3. INDEXES
            # ---------------------------------------------------------
            print()
            print("3. INDEXES")

            cursor.execute(
                """
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'ingest'
                  AND tablename = 'mapping_field'
                ORDER BY indexname;
                """
            )

            rows = cursor.fetchall()

            for row in rows:
                print(
                    f"index={row[0]}\n"
                    f"  {row[1]}"
                )

            # ---------------------------------------------------------
            # 4. FOREIGN KEYS
            # ---------------------------------------------------------
            print()
            print("4. FOREIGN KEYS")

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_schema AS foreign_schema,
                    ccu.table_name AS foreign_table,
                    ccu.column_name AS foreign_column
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                   AND ccu.table_schema = tc.constraint_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'ingest'
                  AND tc.table_name = 'mapping_field'
                ORDER BY tc.constraint_name;
                """
            )

            rows = cursor.fetchall()

            for row in rows:
                print(
                    f"constraint={row[0]} | "
                    f"column={row[1]} | "
                    f"references={row[2]}.{row[3]}."
                    f"{row[4]}"
                )

    print()
    print("=" * 80)
    print("DUPLICATE MAPPING FIELD INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()

