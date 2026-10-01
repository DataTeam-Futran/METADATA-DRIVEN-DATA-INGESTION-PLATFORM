from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONNECTION PROFILE INSPECTION")
    print("=" * 80)

    query = """
        SELECT
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'conn'
          AND table_name = 'connection_profile'
        ORDER BY ordinal_position;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print()
    print("conn.connection_profile columns:")

    for row in rows:
        print(
            f"  {row[0]} | "
            f"type={row[1]} | "
            f"nullable={row[2]}"
        )

    print()
    print("=" * 80)
    print("CONNECTION PROFILE INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()