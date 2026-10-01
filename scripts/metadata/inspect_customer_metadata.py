"""
Customer Metadata Inspection
============================

Purpose
-------
Inspect existing metastore records related to the
demo PostgreSQL source table:

    demo_source_db.public.customer

This script is READ-ONLY.

It does not insert, update, or delete metadata.
"""

from app.db.metastore import get_metastore_connection


def print_section(title: str) -> None:
    print("\n")
    print("=" * 80)
    print(title)
    print("=" * 80)


def main() -> None:

    print_section("CUSTOMER METADATA INSPECTION")

    with get_metastore_connection() as connection:

        # ---------------------------------------------------------
        # 1. SOURCE CONFIG
        # ---------------------------------------------------------

        print_section("1. SOURCE CONFIG")

        query = """
            SELECT
                source_id,
                connection_id,
                source_name,
                source_type,
                source_database,
                source_schema,
                source_object,
                is_active
            FROM ingest.source_config
            WHERE connection_id = %s
            ORDER BY source_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query, (1,))
            rows = cursor.fetchall()

        if not rows:
            print("No source_config record found for connection_id = 1.")

        for row in rows:
            print(
                f"source_id={row[0]} | "
                f"connection_id={row[1]} | "
                f"name={row[2]} | "
                f"type={row[3]} | "
                f"database={row[4]} | "
                f"schema={row[5]} | "
                f"object={row[6]} | "
                f"active={row[7]}"
            )

        # ---------------------------------------------------------
        # 2. DATASET
        # ---------------------------------------------------------

        print_section("2. DATASET")

        query = """
            SELECT
                dataset_id,
                dataset_name,
                source_id,
                target_id,
                is_active
            FROM ingest.dataset
            ORDER BY dataset_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No dataset records found.")

        for row in rows:
            print(
                f"dataset_id={row[0]} | "
                f"name={row[1]} | "
                f"source_id={row[2]} | "
                f"target_id={row[3]} | "
                f"active={row[4]}"
            )

        # ---------------------------------------------------------
        # 3. SCHEMA VERSION
        # ---------------------------------------------------------

        print_section("3. SCHEMA VERSION")

        query = """
            SELECT
                sv.schema_version_id,
                sv.dataset_id,
                d.dataset_name,
                sv.version_number,
                sv.discovery_status,
                sv.discovered_at,
                sv.schema_hash
            FROM ingest.schema_version sv
            LEFT JOIN ingest.dataset d
                ON d.dataset_id = sv.dataset_id
            ORDER BY sv.schema_version_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No schema_version records found.")

        for row in rows:
            print(
                f"schema_version_id={row[0]} | "
                f"dataset_id={row[1]} | "
                f"dataset={row[2]} | "
                f"version={row[3]} | "
                f"status={row[4]} | "
                f"discovered_at={row[5]} | "
                f"hash={row[6]}"
            )

        # ---------------------------------------------------------
        # 4. SCHEMA FIELDS
        # ---------------------------------------------------------

        print_section("4. SCHEMA FIELDS")

        query = """
            SELECT
                schema_field_id,
                schema_version_id,
                ordinal_position,
                column_name,
                native_data_type,
                data_length,
                numeric_precision,
                numeric_scale,
                is_nullable,
                is_primary_key
            FROM ingest.schema_field
            ORDER BY
                schema_version_id,
                ordinal_position;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No schema_field records found.")

        for row in rows:
            print(
                f"schema_field_id={row[0]} | "
                f"schema_version_id={row[1]} | "
                f"position={row[2]} | "
                f"column={row[3]} | "
                f"type={row[4]} | "
                f"length={row[5]} | "
                f"precision={row[6]} | "
                f"scale={row[7]} | "
                f"nullable={row[8]} | "
                f"PK={row[9]}"
            )

        # ---------------------------------------------------------
        # 5. MAP MAPPING
        # ---------------------------------------------------------

        print_section("5. MAP MAPPING")

        query = """
            SELECT
                mapping_id,
                mapping_code,
                mapping_name,
                tenant_id,
                project_id,
                status_code
            FROM map.mapping
            ORDER BY mapping_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No map.mapping records found.")

        for row in rows:
            print(
                f"mapping_id={row[0]} | "
                f"code={row[1]} | "
                f"name={row[2]} | "
                f"tenant_id={row[3]} | "
                f"project_id={row[4]} | "
                f"status={row[5]}"
            )

        # ---------------------------------------------------------
        # 6. MAP MAPPING VERSION
        # ---------------------------------------------------------

        print_section("6. MAP MAPPING VERSION")

        query = """
            SELECT
                mapping_version_id,
                mapping_id,
                primary_source_dataset_id,
                primary_source_schema_version_id,
                target_dataset_id,
                target_schema_version_id,
                datatype_mapping_set_id,
                load_type_code,
                load_strategy_code,
                status_code
            FROM map.mapping_version
            ORDER BY mapping_version_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No map.mapping_version records found.")

        for row in rows:
            print(
                f"mapping_version_id={row[0]} | "
                f"mapping_id={row[1]} | "
                f"source_dataset={row[2]} | "
                f"source_schema_version={row[3]} | "
                f"target_dataset={row[4]} | "
                f"target_schema_version={row[5]} | "
                f"datatype_set={row[6]} | "
                f"load_type={row[7]} | "
                f"strategy={row[8]} | "
                f"status={row[9]}"
            )

        # ---------------------------------------------------------
        # 7. MAP SOURCE
        # ---------------------------------------------------------

        print_section("7. MAP MAPPING SOURCE")

        query = """
            SELECT
                mapping_source_id,
                mapping_version_id,
                dataset_id,
                schema_version_id,
                source_alias,
                sequence_no,
                is_primary
            FROM map.mapping_source
            ORDER BY mapping_source_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No map.mapping_source records found.")

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

        # ---------------------------------------------------------
        # 8. MAP FIELD
        # ---------------------------------------------------------

        print_section("8. MAP MAPPING FIELD")

        query = """
            SELECT
                mapping_field_id,
                mapping_version_id,
                target_field_id,
                mapping_type_code,
                datatype_mapping_rule_id,
                transform_expression,
                null_rule_code,
                default_value,
                key_role_code,
                ordinal_no
            FROM map.mapping_field
            ORDER BY
                mapping_version_id,
                ordinal_no;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No map.mapping_field records found.")

        for row in rows:
            print(
                f"mapping_field_id={row[0]} | "
                f"mapping_version_id={row[1]} | "
                f"target_field_id={row[2]} | "
                f"mapping_type={row[3]} | "
                f"datatype_rule={row[4]} | "
                f"expression={row[5]} | "
                f"null_rule={row[6]} | "
                f"default={row[7]} | "
                f"key_role={row[8]} | "
                f"ordinal={row[9]}"
            )

        # ---------------------------------------------------------
        # 9. MAP FIELD INPUT
        # ---------------------------------------------------------

        print_section("9. MAP MAPPING FIELD INPUT")

        query = """
            SELECT
                mapping_field_input_id,
                mapping_field_id,
                source_field_id,
                source_alias,
                input_role_code,
                ordinal_no
            FROM map.mapping_field_input
            ORDER BY mapping_field_id, ordinal_no;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No map.mapping_field_input records found.")

        for row in rows:
            print(
                f"input_id={row[0]} | "
                f"mapping_field_id={row[1]} | "
                f"source_field_id={row[2]} | "
                f"alias={row[3]} | "
                f"role={row[4]} | "
                f"ordinal={row[5]}"
            )

        # ---------------------------------------------------------
        # 10. TARGET CONFIG
        # ---------------------------------------------------------

        print_section("10. TARGET CONFIG")

        query = """
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
            ORDER BY target_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No target_config records found.")

        for row in rows:
            print(
                f"target_id={row[0]} | "
                f"connection_id={row[1]} | "
                f"name={row[2]} | "
                f"type={row[3]} | "
                f"database={row[4]} | "
                f"schema={row[5]} | "
                f"object={row[6]} | "
                f"active={row[7]}"
            )

        # ---------------------------------------------------------
        # 11. LOAD CONFIG
        # ---------------------------------------------------------

        print_section("11. LOAD CONFIG")

        query = """
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

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No ingest.load_config records found.")

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
        # 12. TARGET LOAD CONFIG
        # ---------------------------------------------------------

        print_section("12. TARGET LOAD CONFIG")

        query = """
            SELECT
                mapping_version_id,
                tenant_id,
                load_method_code,
                commit_size,
                auto_create_target,
                alter_target_policy_code,
                transaction_mode_code,
                write_timeout_seconds,
                target_prepare_action_code,
                target_schema_policy_code,
                constraint_apply_policy_code,
                index_apply_policy_code
            FROM ingest.target_load_config
            ORDER BY mapping_version_id;
        """

        with connection.cursor() as cursor:
            cursor.execute(query)
            rows = cursor.fetchall()

        if not rows:
            print("No ingest.target_load_config records found.")

        for row in rows:
            print(
                f"mapping_version_id={row[0]} | "
                f"tenant_id={row[1]} | "
                f"method={row[2]} | "
                f"commit_size={row[3]} | "
                f"auto_create={row[4]} | "
                f"alter_policy={row[5]} | "
                f"transaction={row[6]} | "
                f"timeout={row[7]} | "
                f"prepare={row[8]} | "
                f"schema_policy={row[9]} | "
                f"constraint_policy={row[10]} | "
                f"index_policy={row[11]}"
            )

    print_section("CUSTOMER METADATA INSPECTION COMPLETED")


if __name__ == "__main__":
    main()