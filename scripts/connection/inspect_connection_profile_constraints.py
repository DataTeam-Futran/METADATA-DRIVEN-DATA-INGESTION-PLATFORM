from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONNECTION PROFILE CONSTRAINT INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            print("\n" + "=" * 80)
            print("COLUMNS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = 'conn'
                  AND table_name = 'connection_profile'
                ORDER BY ordinal_position;
                """
            )

            for row in cursor.fetchall():
                column_name, data_type, nullable, default = row

                print(
                    f"{column_name} | "
                    f"type={data_type} | "
                    f"nullable={nullable} | "
                    f"default={default}"
                )

            print("\n" + "=" * 80)
            print("CONSTRAINTS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    tc.constraint_type
                FROM information_schema.table_constraints tc
                WHERE tc.table_schema = 'conn'
                  AND tc.table_name = 'connection_profile'
                ORDER BY tc.constraint_name;
                """
            )

            for constraint_name, constraint_type in cursor.fetchall():
                print(
                    f"{constraint_name} | "
                    f"type={constraint_type}"
                )

            print("\n" + "=" * 80)
            print("FOREIGN KEY DETAILS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    ccu.table_schema AS referenced_schema,
                    ccu.table_name AS referenced_table,
                    ccu.column_name AS referenced_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                    ON tc.constraint_name = ccu.constraint_name
                   AND tc.table_schema = ccu.table_schema
                WHERE tc.table_schema = 'conn'
                  AND tc.table_name = 'connection_profile'
                  AND tc.constraint_type = 'FOREIGN KEY'
                ORDER BY tc.constraint_name;
                """
            )

            for row in cursor.fetchall():
                print(
                    f"{row[0]} | "
                    f"{row[1]} -> "
                    f"{row[2]}.{row[3]}.{row[4]}"
                )

    print("\n" + "=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()