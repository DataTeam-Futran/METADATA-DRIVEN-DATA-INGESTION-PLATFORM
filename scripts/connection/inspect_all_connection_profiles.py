from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("ALL CONNECTION PROFILES")
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
            status_code
        FROM conn.connection_profile
        ORDER BY connection_id;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

    print()

    if not rows:
        print("No connection profiles found.")
    else:
        for row in rows:
            print(
                f"connection_id={row[0]} | "
                f"name={row[1]} | "
                f"connector_version_id={row[2]} | "
                f"credential_id={row[3]} | "
                f"role={row[4]} | "
                f"host={row[5]} | "
                f"port={row[6]} | "
                f"database={row[7]} | "
                f"status={row[8]}"
            )

    print()
    print("=" * 80)
    print("CONNECTION PROFILE INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()