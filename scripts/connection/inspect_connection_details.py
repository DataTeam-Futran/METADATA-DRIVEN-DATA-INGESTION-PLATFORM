from app.db.metastore import get_metastore_connection


def section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    connection_id = 1

    print("=" * 80)
    print("CONNECTION DETAILS INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            # ---------------------------------------------------------
            # 1. CONNECTION PROFILE
            # ---------------------------------------------------------
            section("1. CONNECTION PROFILE")

            cursor.execute(
                """
                SELECT
                    connection_id,
                    connection_uid,
                    tenant_id,
                    system_id,
                    environment_id,
                    connector_version_id,
                    credential_id,
                    connection_role_code,
                    connection_name,
                    host_name,
                    port_no,
                    database_name,
                    endpoint_url,
                    connect_timeout_seconds,
                    command_timeout_seconds,
                    status_code
                FROM conn.connection_profile
                WHERE connection_id = %s;
                """,
                (connection_id,),
            )

            row = cursor.fetchone()

            if row is None:
                raise LookupError(
                    f"Connection {connection_id} not found."
                )

            columns = [
                "connection_id",
                "connection_uid",
                "tenant_id",
                "system_id",
                "environment_id",
                "connector_version_id",
                "credential_id",
                "connection_role_code",
                "connection_name",
                "host_name",
                "port_no",
                "database_name",
                "endpoint_url",
                "connect_timeout_seconds",
                "command_timeout_seconds",
                "status_code",
            ]

            for name, value in zip(columns, row):
                print(f"{name:<30}: {value}")

            # ---------------------------------------------------------
            # 2. CONNECTION PARAMETERS
            # ---------------------------------------------------------
            section("2. CONNECTION PARAMETERS")

            cursor.execute(
                """
                SELECT
                    connection_id,
                    parameter_code,
                    parameter_value
                FROM conn.connection_parameter
                WHERE connection_id = %s
                ORDER BY parameter_code;
                """,
                (connection_id,),
            )

            rows = cursor.fetchall()

            if not rows:
                print("No connection parameters found.")
            else:
                for row in rows:
                    value = row[2]

                    # Do not expose anything that looks like a secret.
                    if any(
                        keyword in row[1].lower()
                        for keyword in (
                            "password",
                            "secret",
                            "token",
                            "key",
                        )
                    ):
                        value = "***MASKED***"

                    print(
                        f"connection_id={row[0]} | "
                        f"parameter={row[1]} | "
                        f"value={value}"
                    )

            # ---------------------------------------------------------
            # 3. CREDENTIAL REFERENCE
            # ---------------------------------------------------------
            section("3. CREDENTIAL REFERENCE")

            cursor.execute(
                """
                SELECT
                    credential_id,
                    credential_name,
                    secret_provider_code,
                    secret_ref
                FROM conn.credential_ref
                WHERE credential_id = (
                    SELECT credential_id
                    FROM conn.connection_profile
                    WHERE connection_id = %s
                );
                """,
                (connection_id,),
            )

            row = cursor.fetchone()

            if row is None:
                print("No credential reference found.")
            else:
                print(f"credential_id       : {row[0]}")
                print(f"credential_name     : {row[1]}")
                print(f"secret_provider     : {row[2]}")
                print(f"secret_ref          : {row[3]}")

            # ---------------------------------------------------------
            # 4. CONNECTOR VERSION
            # ---------------------------------------------------------
            section("4. CONNECTOR VERSION")

            cursor.execute(
                """
                SELECT
                    connector_version_id,
                    connector_id,
                    version_no,
                    status_code
                FROM conn.connector_version
                WHERE connector_version_id = (
                    SELECT connector_version_id
                    FROM conn.connection_profile
                    WHERE connection_id = %s
                );
                """,
                (connection_id,),
            )

            row = cursor.fetchone()

            if row is None:
                print("No connector version found.")
            else:
                print(
                    f"connector_version_id={row[0]} | "
                    f"connector_id={row[1]} | "
                    f"version={row[2]} | "
                    f"status={row[3]}"
                )

    section("CONNECTION DETAILS INSPECTION COMPLETED")


if __name__ == "__main__":
    main()