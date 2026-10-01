from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONNECTION PROFILE RECORD")
    print("=" * 80)

    query = """
        SELECT
            connection_id,
            connection_name,
            connector_version_id,
            credential_id,
            connection_role_code,
            host_name,
            port_no,
            database_name,
            connect_timeout_seconds,
            command_timeout_seconds,
            status_code
        FROM conn.connection_profile
        WHERE connection_id = %s;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (1,))
            row = cursor.fetchone()

    if row is None:
        raise LookupError(
            "Connection profile ID 1 was not found."
        )

    print()
    print(f"Connection ID        : {row[0]}")
    print(f"Connection Name      : {row[1]}")
    print(f"Connector Version ID : {row[2]}")
    print(f"Credential ID        : {row[3]}")
    print(f"Role                 : {row[4]}")
    print(f"Host                 : {row[5]}")
    print(f"Port                 : {row[6]}")
    print(f"Database             : {row[7]}")
    print(f"Connect Timeout      : {row[8]}")
    print(f"Command Timeout      : {row[9]}")
    print(f"Status               : {row[10]}")

    print()
    print("=" * 80)
    print("CONNECTION PROFILE RECORD COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()



