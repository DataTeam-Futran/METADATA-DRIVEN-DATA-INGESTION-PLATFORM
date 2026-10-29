from app.db.metastore import get_metastore_connection

TARGET_NAME = "Demo SQL Server Target Connection"
CREDENTIAL_NAME = "MDIP SQL Server Target Credential"

TENANT_ID = 1
SYSTEM_ID = 1
ENVIRONMENT_ID = 1
CONNECTOR_VERSION_ID = 1
AUTH_METHOD_ID = 1

TARGET_HOST = "192.168.11.91"
TARGET_PORT = 1433
TARGET_DATABASE = "Target_db"
TARGET_USERNAME = "mdip_ingestion"

SECRET_PROVIDER = "DEMO"
SECRET_REF = "SQLSERVER_DEV_SECRET"


def main():
    print("=" * 70)
    print("CREATE SQL SERVER TARGET CONNECTION")
    print("=" * 70)

    with get_metastore_connection() as connection:
        try:
            with connection.cursor() as cursor:
                # Validate the connector version and target capability.
                cursor.execute("""
                    SELECT c.connector_code, cv.status_code, c.supports_target
                    FROM conn.connector_version cv
                    JOIN conn.connector c
                      ON c.connector_id = cv.connector_id
                    WHERE cv.connector_version_id = %s;
                """, (CONNECTOR_VERSION_ID,))
                connector = cursor.fetchone()

                if not connector:
                    raise RuntimeError("SQL Server connector version not found.")

                if connector[0] != "SQL_SERVER_CONNECTOR":
                    raise RuntimeError("Connector version is not SQL Server.")

                if connector[1] != "ACTIVE" or not connector[2]:
                    raise RuntimeError(
                        "SQL Server connector must be ACTIVE and support TARGET."
                    )

                # Validate the authentication method.
                cursor.execute("""
                    SELECT auth_method_code, status_code
                    FROM conn.connector_auth_method
                    WHERE auth_method_id = %s
                      AND connector_id = 1;
                """, (AUTH_METHOD_ID,))
                auth = cursor.fetchone()

                if not auth or auth != ("SQL_PASSWORD", "ACTIVE"):
                    raise RuntimeError("SQL_PASSWORD authentication is not active.")

                # Stop if this named connection already exists.
                cursor.execute("""
                    SELECT connection_id, connector_version_id,
                           database_name, connection_role_code
                    FROM conn.connection_profile
                    WHERE tenant_id = %s
                      AND system_id = %s
                      AND environment_id = %s
                      AND connection_name = %s;
                """, (TENANT_ID, SYSTEM_ID, ENVIRONMENT_ID, TARGET_NAME))

                existing = cursor.fetchone()
                if existing:
                    raise RuntimeError(
                        f"Connection name already exists: {existing}. "
                        "No metadata was changed."
                    )

                # Reuse only our specifically named credential if it already
                # exists and matches the intended SQL Server configuration.
                cursor.execute("""
                    SELECT credential_id, tenant_id, auth_method_id,
                           secret_provider_code, secret_ref, status_code
                    FROM conn.credential_ref
                    WHERE credential_name = %s;
                """, (CREDENTIAL_NAME,))
                credential = cursor.fetchone()

                if credential:
                    expected = (
                        TENANT_ID, AUTH_METHOD_ID,
                        SECRET_PROVIDER, SECRET_REF, "ACTIVE"
                    )
                    if credential[1:] != expected:
                        raise RuntimeError(
                            "Existing credential name has different metadata. "
                            "No metadata was changed."
                        )
                    credential_id = credential[0]
                    print(f"Using existing matching credential ID: {credential_id}")
                else:
                    cursor.execute("""
                        INSERT INTO conn.credential_ref (
                            tenant_id,
                            auth_method_id,
                            credential_name,
                            secret_provider_code,
                            secret_ref,
                            status_code
                        )
                        VALUES (%s, %s, %s, %s, %s, 'ACTIVE')
                        RETURNING credential_id;
                    """, (
                        TENANT_ID,
                        AUTH_METHOD_ID,
                        CREDENTIAL_NAME,
                        SECRET_PROVIDER,
                        SECRET_REF,
                    ))
                    credential_id = cursor.fetchone()[0]
                    print(f"New credential reference created: {credential_id}")

                # Create the separate SQL Server TARGET profile.
                cursor.execute("""
                    INSERT INTO conn.connection_profile (
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
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, 'TARGET', %s,
                        %s, %s, %s, %s, 30, 600, 'ACTIVE'
                    )
                    RETURNING connection_id;
                """, (
                    TENANT_ID,
                    SYSTEM_ID,
                    ENVIRONMENT_ID,
                    CONNECTOR_VERSION_ID,
                    credential_id,
                    TARGET_NAME,
                    TARGET_HOST,
                    TARGET_PORT,
                    TARGET_DATABASE,
                    f"mssql://{TARGET_HOST}:{TARGET_PORT}/{TARGET_DATABASE}",
                ))
                target_connection_id = cursor.fetchone()[0]

                # Store connection options, never the password.
                parameters = [
                    ("username", TARGET_USERNAME, "STRING", False),
                    ("auth_method", "SQL_PASSWORD", "STRING", False),
                    ("encrypt", "yes", "STRING", False),
                    ("trust_server_certificate", "yes", "STRING", False),
                ]

                for name, value, value_type, is_secret_ref in parameters:
                    cursor.execute("""
                        INSERT INTO conn.connection_parameter (
                            connection_id,
                            parameter_name,
                            parameter_value,
                            value_type_code,
                            is_secret_ref,
                            environment_override
                        )
                        VALUES (%s, %s, %s, %s, %s, false);
                    """, (
                        target_connection_id,
                        name,
                        value,
                        value_type,
                        is_secret_ref,
                    ))

                # Verify the new profile before committing.
                cursor.execute("""
                    SELECT connection_id, connection_name,
                           connector_version_id, credential_id,
                           connection_role_code, host_name, port_no,
                           database_name, status_code
                    FROM conn.connection_profile
                    WHERE connection_id = %s;
                """, (target_connection_id,))
                print("\nNEW TARGET PROFILE")
                print(cursor.fetchone())

                connection.commit()
                print("\nSUCCESS: SQL Server target metadata committed.")
                print(f"New target connection ID: {target_connection_id}")
                print("Password was not inserted into the metadata store.")

        except Exception:
            connection.rollback()
            raise


if __name__ == "__main__":
    main()
