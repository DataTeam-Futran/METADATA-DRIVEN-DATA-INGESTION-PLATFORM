from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("MAPPING FIELD DEPENDENCY CHECK")
    print("=" * 80)

    query = """
        SELECT
            tc.table_schema,
            tc.table_name,
            kcu.column_name,
            ccu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema = tc.constraint_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND ccu.table_schema = 'ingest'
          AND ccu.table_name = 'mapping_field'
        ORDER BY
            tc.table_schema,
            tc.table_name,
            kcu.column_name;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print()
    print("FOREIGN KEYS REFERENCING ingest.mapping_field")
    print()

    if not rows:
        print("No foreign-key dependencies found.")
    else:
        for row in rows:
            print(
                f"table={row[0]}.{row[1]} | "
                f"column={row[2]} | "
                f"references mapping_field.{row[3]}"
            )

    print()
    print("=" * 80)
    print("DEPENDENCY CHECK COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()