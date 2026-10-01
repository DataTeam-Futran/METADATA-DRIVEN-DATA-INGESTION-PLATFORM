import psycopg

from app.credentials.resolver import CredentialResolver


def main() -> None:
    credential_id = 1

    host = "192.168.11.91"
    port = 5432
    database = "ingestion_metastore"
    username = "postgres"

    print("=" * 80)
    print("TARGET DATABASE CREDENTIAL TEST")
    print("=" * 80)

    resolver = CredentialResolver()

    password = resolver.resolve(credential_id)

    print(f"\nCredential ID : {credential_id}")
    print(f"Host          : {host}")
    print(f"Port          : {port}")
    print(f"Database      : {database}")
    print(f"Username      : {username}")
    print(f"Secret found  : {bool(password)}")

    try:
        with psycopg.connect(
            host=host,
            port=port,
            dbname=database,
            user=username,
            password=password,
            connect_timeout=10,
        ) as connection:

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        current_database(),
                        current_user;
                    """
                )

                database_name, current_user = cursor.fetchone()

        print("\nTARGET CONNECTION SUCCESSFUL")
        print(f"Database : {database_name}")
        print(f"User     : {current_user}")

    except Exception as exc:
        print("\nTARGET CONNECTION FAILED")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error     : {exc}")
        raise

    print("\n" + "=" * 80)
    print("TARGET DATABASE CREDENTIAL TEST COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()