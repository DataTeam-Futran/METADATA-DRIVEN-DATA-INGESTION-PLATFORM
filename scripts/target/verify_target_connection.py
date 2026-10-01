"""
Verify that the TARGET connection created by the previous script
actually exists in the metadata database.

Why this script is needed
-------------------------
The target connection creation script reported:

    connection_id = 10

However, update_target_config.py cannot find connection 10.

Before changing any metadata, we need to determine whether:

1. Connection 10 was actually committed.
2. We are connected to the same metastore database.
3. The connection exists with TARGET role.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Read the target connection directly from the metadata store
    and verify its existence.
    """

    print("=" * 80)
    print("VERIFY TARGET CONNECTION")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # Connect to the application's configured metadata/control database.
    #
    # We deliberately use the same get_metastore_connection() used by the
    # application so that this test follows the actual runtime configuration.
    # -----------------------------------------------------------------------
    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # ----------------------------------------------------------------
            # First identify which database and PostgreSQL user this script
            # is actually connected to.
            #
            # Why:
            # If create_target_connection.py and this script are connecting
            # to different databases, connection_id=10 may exist somewhere
            # else.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    inet_server_addr(),
                    inet_server_port();
                """
            )

            database_name, username, server_address, server_port = (
                cursor.fetchone()
            )

            print("\nCurrent metastore connection:")
            print(f"Database : {database_name}")
            print(f"User     : {username}")
            print(f"Server   : {server_address}")
            print(f"Port     : {server_port}")

            # ----------------------------------------------------------------
            # Check specifically for connection_id=10.
            # ----------------------------------------------------------------
            cursor.execute(
                """
                SELECT
                    connection_id,
                    connection_name,
                    connection_role_code,
                    tenant_id,
                    system_id,
                    environment_id,
                    connector_version_id,
                    credential_id,
                    host_name,
                    port_no,
                    database_name,
                    status_code
                FROM conn.connection_profile
                WHERE connection_id = %s;
                """,
                (10,),
            )

            target_connection = cursor.fetchone()

            print("\n" + "=" * 80)
            print("CONNECTION ID 10")
            print("=" * 80)

            if target_connection is None:
                print("\nConnection ID 10 was NOT found.")

                # ------------------------------------------------------------
                # Since the specific ID was not found, list all existing
                # connections. This tells us whether the insert disappeared
                # or whether the sequence generated a different ID.
                # ------------------------------------------------------------

                cursor.execute(
                    """
                    SELECT
                        connection_id,
                        connection_name,
                        connection_role_code,
                        database_name,
                        status_code
                    FROM conn.connection_profile
                    ORDER BY connection_id;
                    """
                )

                print("\nExisting connections:")

                for row in cursor.fetchall():
                    print(
                        f"connection_id={row[0]} | "
                        f"name={row[1]} | "
                        f"role={row[2]} | "
                        f"database={row[3]} | "
                        f"status={row[4]}"
                    )

            else:
                (
                    connection_id,
                    connection_name,
                    role,
                    tenant_id,
                    system_id,
                    environment_id,
                    connector_version_id,
                    credential_id,
                    host_name,
                    port_no,
                    target_database,
                    status,
                ) = target_connection

                print(
                    f"\nConnection ID     : {connection_id}"
                )
                print(
                    f"Connection Name   : {connection_name}"
                )
                print(
                    f"Role              : {role}"
                )
                print(
                    f"Tenant ID         : {tenant_id}"
                )
                print(
                    f"System ID         : {system_id}"
                )
                print(
                    f"Environment ID    : {environment_id}"
                )
                print(
                    f"Connector Version : {connector_version_id}"
                )
                print(
                    f"Credential ID     : {credential_id}"
                )
                print(
                    f"Host              : {host_name}"
                )
                print(
                    f"Port              : {port_no}"
                )
                print(
                    f"Database          : {target_database}"
                )
                print(
                    f"Status            : {status}"
                )

    print("\n" + "=" * 80)
    print("VERIFICATION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()