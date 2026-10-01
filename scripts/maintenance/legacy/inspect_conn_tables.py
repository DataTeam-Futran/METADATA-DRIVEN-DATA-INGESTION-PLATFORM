from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONN SCHEMA INSPECTION")
    print("=" * 80)

    query = """
        SELECT
            table_name
        FROM information_schema.tables
        WHERE table_schema = 'conn'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print()

    if not rows:
        print("No tables found in schema conn.")
    else:
        print("Tables in conn schema:")
        for row in rows:
            print(f"  {row[0]}")

    print()
    print("=" * 80)
    print("CONN SCHEMA INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()