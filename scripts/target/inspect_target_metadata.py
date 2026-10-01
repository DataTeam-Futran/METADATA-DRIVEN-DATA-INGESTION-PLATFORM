from app.db.metastore import get_metastore_connection


def section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    section("TARGET METADATA INSPECTION")

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            # ---------------------------------------------------------
            # 1. TARGET CONFIG
            # ---------------------------------------------------------
            section("1. TARGET CONFIG")

            cursor.execute(
                """
                SELECT
                    target_id,
                    connection_id,
                    target_name,
                    target_type,
                    target_database,
                    target_schema,
                    target_object,
                    is_active
                FROM ingest.target_config
                WHERE target_id = 1;
                """
            )

            row = cursor.fetchone()

            if row is None:
                print("Target ID 1 not found.")
                return

            print(f"target_id      = {row[0]}")
            print(f"connection_id  = {row[1]}")
            print(f"target_name    = {row[2]}")
            print(f"target_type    = {row[3]}")
            print(f"database       = {row[4]}")
            print(f"schema         = {row[5]}")
            print(f"object         = {row[6]}")
            print(f"active         = {row[7]}")

            # ---------------------------------------------------------
            # 2. TARGET SCHEMA VERSION REFERENCES
            # ---------------------------------------------------------
            section("2. TARGET SCHEMA VERSION REFERENCES")

            cursor.execute(
                """
                SELECT
                    mapping_version_id,
                    mapping_id,
                    source_schema_version_id,
                    target_schema_version_id,
                    version_number,
                    status
                FROM ingest.mapping_version
                WHERE mapping_version_id = 1;
                """
            )

            row = cursor.fetchone()

            if row is None:
                print("Mapping version 1 not found.")
            else:
                print(f"mapping_version_id       = {row[0]}")
                print(f"mapping_id               = {row[1]}")
                print(f"source_schema_version_id = {row[2]}")
                print(f"target_schema_version_id = {row[3]}")
                print(f"version                  = {row[4]}")
                print(f"status                   = {row[5]}")

            # ---------------------------------------------------------
            # 3. EXISTING TARGET TABLE
            # ---------------------------------------------------------
            section("3. EXISTING TARGET TABLE")

            cursor.execute(
                """
                SELECT
                    table_schema,
                    table_name
                FROM information_schema.tables
                WHERE table_schema = 'warehouse'
                  AND table_name = 'employee_target';
                """
            )

            row = cursor.fetchone()

            if row is None:
                print("Target table warehouse.employee_target does NOT exist.")
            else:
                print(
                    f"Target table exists: "
                    f"{row[0]}.{row[1]}"
                )

            # ---------------------------------------------------------
            # 4. TARGET TABLE COLUMNS
            # ---------------------------------------------------------
            section("4. TARGET TABLE COLUMNS")

            cursor.execute(
                """
                SELECT
                    ordinal_position,
                    column_name,
                    data_type,
                    character_maximum_length,
                    numeric_precision,
                    numeric_scale,
                    is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'warehouse'
                  AND table_name = 'employee_target'
                ORDER BY ordinal_position;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No target columns found.")
            else:
                for row in rows:
                    print(
                        f"position={row[0]} | "
                        f"column={row[1]} | "
                        f"type={row[2]} | "
                        f"length={row[3]} | "
                        f"precision={row[4]} | "
                        f"scale={row[5]} | "
                        f"nullable={row[6]}"
                    )

            # ---------------------------------------------------------
            # 5. TARGET SCHEMA METADATA
            # ---------------------------------------------------------
            section("5. TARGET SCHEMA METADATA")

            cursor.execute(
                """
                SELECT
                    schema_version_id,
                    dataset_id,
                    version_number,
                    discovery_status,
                    discovered_at,
                    schema_hash
                FROM ingest.schema_version
                WHERE schema_version_id IS NOT NULL
                ORDER BY schema_version_id;
                """
            )

            rows = cursor.fetchall()

            for row in rows:
                print(
                    f"schema_version_id={row[0]} | "
                    f"dataset_id={row[1]} | "
                    f"version={row[2]} | "
                    f"status={row[3]} | "
                    f"discovered={row[4]} | "
                    f"hash={row[5]}"
                )

    section("TARGET METADATA INSPECTION COMPLETED")


if __name__ == "__main__":
    main()