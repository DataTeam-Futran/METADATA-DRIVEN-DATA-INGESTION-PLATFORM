from app.db.metastore import get_metastore_connection


def main() -> None:
    print("=" * 80)
    print("CONNECTION IDENTITY INSPECTION")
    print("=" * 80)

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            print("\n" + "=" * 80)
            print("EXISTING CONNECTION IDENTITIES")
            print("=" * 80)

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
                    endpoint_url,
                    connect_timeout_seconds,
                    command_timeout_seconds,
                    status_code
                FROM conn.connection_profile
                ORDER BY connection_id;
                """
            )

            columns = [column[0] for column in cursor.description]

            print("\n" + " | ".join(columns))

            for row in cursor.fetchall():
                print(" | ".join(str(value) for value in row))

            print("\n" + "=" * 80)
            print("UNIQUE CONSTRAINT COLUMNS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    tc.constraint_name,
                    kcu.column_name,
                    kcu.ordinal_position
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema = kcu.table_schema
                   AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = 'conn'
                  AND tc.table_name = 'connection_profile'
                  AND tc.constraint_type = 'UNIQUE'
                ORDER BY
                    tc.constraint_name,
                    kcu.ordinal_position;
                """
            )

            for constraint_name, column_name, ordinal_position in cursor.fetchall():
                print(
                    f"{constraint_name} | "
                    f"position={ordinal_position} | "
                    f"column={column_name}"
                )

            print("\n" + "=" * 80)
            print("CHECK CONSTRAINT DEFINITIONS")
            print("=" * 80)

            cursor.execute(
                """
                SELECT
                    conname,
                    pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'conn.connection_profile'::regclass
                  AND contype = 'c'
                ORDER BY conname;
                """
            )

            for constraint_name, definition in cursor.fetchall():
                print(f"{constraint_name} | {definition}")

    print("\n" + "=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()