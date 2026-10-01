from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("TARGET CONNECTION INSPECTION")
    print("=" * 80)

    query = """
        SELECT
            connection_id,
            connection_name,
            connector_code,
            host_name,
            port_no,
            database_name,
            role_code,
            credential_id
        FROM conn.connection
        WHERE connection_id = %s;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (1,))
            row = cursor.fetchone()

    if row is None:
        raise LookupError("Connection ID 1 was not found.")

    print()
    print(f"Connection ID    : {row[0]}")
    print(f"Connection Name  : {row[1]}")
    print(f"Connector        : {row[2]}")
    print(f"Host             : {row[3]}")
    print(f"Port             : {row[4]}")
    print(f"Database         : {row[5]}")
    print(f"Role             : {row[6]}")
    print(f"Credential ID    : {row[7]}")

    print()
    print("=" * 80)
    print("TARGET CONNECTION INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()