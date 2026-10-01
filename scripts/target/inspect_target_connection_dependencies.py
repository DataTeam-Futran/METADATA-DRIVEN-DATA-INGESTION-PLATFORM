from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("TARGET CONNECTION DEPENDENCY INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            print("\n" + "=" * 80)
            print("CREDENTIAL REFERENCES")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    credential_id,
                    credential_name,
                    secret_provider_code,
                    secret_ref
                FROM conn.credential_ref
                ORDER BY credential_id;
                """
            )

            credentials = cursor.fetchall()

            for row in credentials:
                credential_id, name, provider, secret_ref = row

                print(
                    f"credential_id={credential_id} | "
                    f"name={name} | "
                    f"provider={provider} | "
                    f"secret_ref={secret_ref}"
                )

            print("\n" + "=" * 80)
            print("CONNECTOR VERSIONS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    connector_version_id,
                    connector_id,
                    version,
                    status_code
                FROM conn.connector_version
                ORDER BY connector_version_id;
                """
            )

            versions = cursor.fetchall()

            for row in versions:
                print(
                    f"connector_version_id={row[0]} | "
                    f"connector_id={row[1]} | "
                    f"version={row[2]} | "
                    f"status={row[3]}"
                )

    print("\n" + "=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()