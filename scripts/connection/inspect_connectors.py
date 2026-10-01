from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONNECTOR TABLE INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            print("\n" + "=" * 80)
            print("CONNECTOR COLUMNS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'conn'
                  AND table_name = 'connector'
                ORDER BY ordinal_position;
                """
            )

            for column_name, data_type, nullable in cursor.fetchall():
                print(
                    f"{column_name} | "
                    f"type={data_type} | "
                    f"nullable={nullable}"
                )

            print("\n" + "=" * 80)
            print("CONNECTOR DATA")
            print("=" * 80)

            cursor.execute(
                """
                SELECT *
                FROM conn.connector
                ORDER BY connector_id;
                """
            )

            column_names = [column[0] for column in cursor.description]

            print("\nColumns:")
            print(" | ".join(column_names))

            for row in cursor.fetchall():
                print(" | ".join(str(value) for value in row))

    print("\n" + "=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()