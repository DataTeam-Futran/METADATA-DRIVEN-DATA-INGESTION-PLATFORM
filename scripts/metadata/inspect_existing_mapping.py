from app.db.metastore import get_metastore_connection


def print_section(title: str) -> None:
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:
    print_section("EXISTING MAPPING INSPECTION")

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:

            # ---------------------------------------------------------
            # 1. INGEST LOAD CONFIG
            # ---------------------------------------------------------
            print_section("1. INGEST LOAD CONFIG")

            cursor.execute(
                """
                SELECT
                    load_config_id,
                    mapping_version_id,
                    load_type_code,
                    batch_size,
                    truncate_before_load,
                    is_active
                FROM ingest.load_config
                ORDER BY load_config_id;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No ingest.load_config records found.")
            else:
                for row in rows:
                    print(
                        f"load_config_id={row[0]} | "
                        f"mapping_version_id={row[1]} | "
                        f"load_type={row[2]} | "
                        f"batch_size={row[3]} | "
                        f"truncate={row[4]} | "
                        f"active={row[5]}"
                    )

            # ---------------------------------------------------------
            # 2. INGEST MAPPING
            # ---------------------------------------------------------
            print_section("2. INGEST MAPPING")

            cursor.execute(
                """
                SELECT
                    mapping_id,
                    mapping_name,
                    dataset_id,
                    description,
                    is_active
                FROM ingest.mapping
                ORDER BY mapping_id;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No ingest.mapping records found.")
            else:
                for row in rows:
                    print(
                        f"mapping_id={row[0]} | "
                        f"name={row[1]} | "
                        f"dataset_id={row[2]} | "
                        f"description={row[3]} | "
                        f"active={row[4]}"
                    )

            # ---------------------------------------------------------
            # 3. INGEST MAPPING VERSION
            # ---------------------------------------------------------
            print_section("3. INGEST MAPPING VERSION")

            cursor.execute(
                """
                SELECT
                    mapping_version_id,
                    mapping_id,
                    source_schema_version_id,
                    target_schema_version_id,
                    version_number,
                    status,
                    config_hash,
                    created_at,
                    approved_at
                FROM ingest.mapping_version
                ORDER BY mapping_version_id;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No ingest.mapping_version records found.")
            else:
                for row in rows:
                    print(
                        f"mapping_version_id={row[0]} | "
                        f"mapping_id={row[1]} | "
                        f"source_schema_version_id={row[2]} | "
                        f"target_schema_version_id={row[3]} | "
                        f"version={row[4]} | "
                        f"status={row[5]} | "
                        f"hash={row[6]} | "
                        f"created={row[7]} | "
                        f"approved={row[8]}"
                    )

            # ---------------------------------------------------------
            # 4. INGEST MAPPING FIELD
            # ---------------------------------------------------------
            print_section("4. INGEST MAPPING FIELD")

            cursor.execute(
                """
                SELECT
                    mapping_field_id,
                    mapping_version_id,
                    source_field_name,
                    target_field_name,
                    target_data_type,
                    transformation_type,
                    transformation_expression,
                    is_key,
                    is_required,
                    ordinal_position
                FROM ingest.mapping_field
                ORDER BY mapping_version_id, ordinal_position;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No ingest.mapping_field records found.")
            else:
                for row in rows:
                    print(
                        f"mapping_field_id={row[0]} | "
                        f"mapping_version_id={row[1]} | "
                        f"source={row[2]} | "
                        f"target={row[3]} | "
                        f"datatype={row[4]} | "
                        f"transform={row[5]} | "
                        f"expression={row[6]} | "
                        f"key={row[7]} | "
                        f"required={row[8]} | "
                        f"position={row[9]}"
                    )

            # ---------------------------------------------------------
            # 5. INGEST MAPPING SOURCE
            # ---------------------------------------------------------
            print_section("5. INGEST MAPPING SOURCE")

            cursor.execute(
                """
                SELECT
                    mapping_source_id,
                    mapping_version_id,
                    dataset_id,
                    schema_version_id,
                    source_alias,
                    sequence_no,
                    is_primary
                FROM ingest.mapping_source
                ORDER BY mapping_version_id, sequence_no;
                """
            )

            rows = cursor.fetchall()

            if not rows:
                print("No ingest.mapping_source records found.")
            else:
                for row in rows:
                    print(
                        f"mapping_source_id={row[0]} | "
                        f"mapping_version_id={row[1]} | "
                        f"dataset_id={row[2]} | "
                        f"schema_version_id={row[3]} | "
                        f"alias={row[4]} | "
                        f"sequence={row[5]} | "
                        f"primary={row[6]}"
                    )

    print()
    print("=" * 80)
    print("EXISTING MAPPING INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()