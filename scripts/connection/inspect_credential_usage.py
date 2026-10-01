from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CREDENTIAL USAGE INSPECTION")
    print("=" * 80)

    query = """
        SELECT
            cp.connection_id,
            cp.connection_name,
            cp.connection_role_code,
            cp.database_name,
            cp.credential_id,
            cr.credential_name,
            cr.secret_provider_code,
            cr.secret_ref
        FROM conn.connection_profile cp
        LEFT JOIN conn.credential_ref cr
            ON cp.credential_id = cr.credential_id
        ORDER BY cp.connection_id;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)

            rows = cursor.fetchall()

    print("\nExisting connection → credential mapping:\n")

    for row in rows:
        (
            connection_id,
            connection_name,
            role,
            database_name,
            credential_id,
            credential_name,
            provider,
            secret_ref,
        ) = row

        print(
            f"connection_id={connection_id} | "
            f"name={connection_name} | "
            f"role={role} | "
            f"database={database_name} | "
            f"credential_id={credential_id} | "
            f"credential_name={credential_name} | "
            f"provider={provider} | "
            f"secret_ref={secret_ref}"
        )

    print("\n" + "=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()