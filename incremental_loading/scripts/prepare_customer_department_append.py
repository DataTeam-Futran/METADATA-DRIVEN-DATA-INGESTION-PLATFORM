"""Prepare the Customer and Department PostgreSQL append-load objects."""

from typing import Any

from app.db.metastore import get_metastore_connection
from app.runtime.connection_resolver import RuntimeConnectionResolver


SOURCE_CONNECTION_ID = 18
REFERENCE_SOURCE_CONNECTION_ID = 1
TARGET_CONNECTION_ID = 11
SOURCE_SCHEMA = "public"
TARGET_SCHEMA = "warehouse"
WATERMARK_COLUMN = "last_modified_at"

TABLES = (
    {
        "source_code": "INCREMENTAL_SOURCE_CUSTOMER",
        "source_name": "Incremental Customer Source",
        "source_table": "customer",
        "target_code": "INCREMENTAL_TARGET_CUSTOMER",
        "target_name": "Incremental Customer Target",
        "target_table": "customer_incremental_target",
        "columns": (
            ("customerid", "INTEGER"),
            ("firstname", "TEXT"),
            ("lastname", "TEXT"),
            ("email", "TEXT"),
            ("phone", "TEXT"),
            ("departmentid", "INTEGER"),
            (WATERMARK_COLUMN, "TIMESTAMPTZ"),
        ),
    },
    {
        "source_code": "INCREMENTAL_SOURCE_DEPARTMENT",
        "source_name": "Incremental Department Source",
        "source_table": "department",
        "target_code": "INCREMENTAL_TARGET_DEPARTMENT",
        "target_name": "Incremental Department Target",
        "target_table": "department_incremental_target",
        "columns": (
            ("departmentid", "INTEGER"),
            ("departmentname", "TEXT"),
            ("location", "TEXT"),
            (WATERMARK_COLUMN, "TIMESTAMPTZ"),
        ),
    },
)


def get_profiles(connection: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    query = """
        SELECT
            connection_id,
            tenant_id,
            system_id,
            environment_id,
            connector_version_id,
            credential_id,
            connection_role_code,
            host_name,
            port_no,
            database_name,
            status_code
        FROM conn.connection_profile
        WHERE connection_id = %s;
    """
    profiles = []
    with connection.cursor() as cursor:
        for connection_id in (
            SOURCE_CONNECTION_ID,
            TARGET_CONNECTION_ID,
        ):
            cursor.execute(query, (connection_id,))
            row = cursor.fetchone()
            if row is None:
                raise LookupError(
                    f"Connection profile {connection_id} was not found."
                )
            profiles.append(
                dict(
                    zip(
                        (
                            "connection_id",
                            "tenant_id",
                            "system_id",
                            "environment_id",
                            "connector_version_id",
                            "credential_id",
                            "connection_role_code",
                            "host_name",
                            "port_no",
                            "database_name",
                            "status_code",
                        ),
                        row,
                    )
                )
            )
    return profiles[0], profiles[1]


def ensure_source_username() -> None:
    """Copy only the username from the matching source profile if absent."""
    with get_metastore_connection() as connection:
        try:
            query = """
                SELECT
                    connection_id,
                    tenant_id,
                    system_id,
                    environment_id,
                    credential_id,
                    connection_role_code,
                    host_name,
                    port_no,
                    status_code
                FROM conn.connection_profile
                WHERE connection_id = %s;
            """
            with connection.cursor() as cursor:
                cursor.execute(query, (SOURCE_CONNECTION_ID,))
                source = cursor.fetchone()
                cursor.execute(query, (REFERENCE_SOURCE_CONNECTION_ID,))
                reference = cursor.fetchone()

                if source is None or reference is None:
                    raise LookupError(
                        "Source connection 18 or reference connection 1 is missing."
                    )

                if source[5] not in ("SOURCE", "BOTH"):
                    raise ValueError("Connection 18 is not a source profile.")
                if source[8] != "ACTIVE" or reference[8] != "ACTIVE":
                    raise ValueError("Both source profiles must be ACTIVE.")
                if (source[1], source[2], source[3], source[4], source[6], source[7]) != (
                    reference[1],
                    reference[2],
                    reference[3],
                    reference[4],
                    reference[6],
                    reference[7],
                ):
                    raise ValueError(
                        "Connection 18 does not share tenant, system, environment, "
                        "credential, host, and port with connection 1."
                    )

                cursor.execute(
                    """
                    SELECT parameter_value
                    FROM conn.connection_parameter
                    WHERE connection_id = %s
                      AND parameter_name = 'username'
                    LIMIT 1;
                    """,
                    (SOURCE_CONNECTION_ID,),
                )
                existing_username = cursor.fetchone()
                if existing_username and existing_username[0]:
                    connection.commit()
                    return

                cursor.execute(
                    """
                    SELECT parameter_value, value_type_code, is_secret_ref
                    FROM conn.connection_parameter
                    WHERE connection_id = %s
                      AND parameter_name = 'username'
                    LIMIT 1;
                    """,
                    (REFERENCE_SOURCE_CONNECTION_ID,),
                )
                username = cursor.fetchone()
                if username is None or not username[0]:
                    raise ValueError(
                        "Reference connection 1 has no configured username."
                    )

                cursor.execute(
                    """
                    INSERT INTO conn.connection_parameter (
                        connection_id,
                        parameter_name,
                        parameter_value,
                        value_type_code,
                        is_secret_ref,
                        environment_override
                    )
                    VALUES (%s, 'username', %s, %s, %s, FALSE);
                    """,
                    (
                        SOURCE_CONNECTION_ID,
                        username[0],
                        username[1],
                        username[2],
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def add_source_watermarks() -> None:
    connector = RuntimeConnectionResolver().resolve(SOURCE_CONNECTION_ID)
    connector.connect()
    connection = connector._require_connection()
    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                source_table = quote_identifier(table["source_table"])
                source_schema = quote_identifier(SOURCE_SCHEMA)
                cursor.execute(
                    f"ALTER TABLE {source_schema}.{source_table} "
                    f"ADD COLUMN IF NOT EXISTS {quote_identifier(WATERMARK_COLUMN)} "
                    "TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP;"
                )
            cursor.execute(
                """
                CREATE OR REPLACE FUNCTION public.mdip_set_last_modified_at()
                RETURNS trigger
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    NEW.last_modified_at = clock_timestamp();
                    RETURN NEW;
                END;
                $$;
                """
            )
            for table in TABLES:
                source_table = quote_identifier(table["source_table"])
                trigger_name = quote_identifier(
                    f"mdip_{table['source_table']}_watermark"
                )
                cursor.execute(
                    f"DROP TRIGGER IF EXISTS {trigger_name} "
                    f"ON {quote_identifier(SOURCE_SCHEMA)}.{source_table};"
                )
                cursor.execute(
                    f"CREATE TRIGGER {trigger_name} "
                    f"BEFORE INSERT OR UPDATE ON "
                    f"{quote_identifier(SOURCE_SCHEMA)}.{source_table} "
                    "FOR EACH ROW EXECUTE FUNCTION "
                    "public.mdip_set_last_modified_at();"
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connector.close()


def create_target_tables() -> None:
    connector = RuntimeConnectionResolver().resolve(TARGET_CONNECTION_ID)
    connector.connect()
    connection = connector._require_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(TARGET_SCHEMA)};"
            )
            for table in TABLES:
                definitions = ", ".join(
                    f"{quote_identifier(column)} {data_type}"
                    + (" NOT NULL" if column == WATERMARK_COLUMN else "")
                    for column, data_type in table["columns"]
                )
                target_table = quote_identifier(table["target_table"])
                target_schema = quote_identifier(TARGET_SCHEMA)
                cursor.execute(
                    f"CREATE TABLE IF NOT EXISTS {target_schema}.{target_table} "
                    f"({definitions});"
                )
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS "
                    f"{quote_identifier(table['target_table'] + '_watermark_idx')} "
                    f"ON {target_schema}.{target_table} "
                    f"({quote_identifier(WATERMARK_COLUMN)});"
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connector.close()


def ensure_dataset(
    connection: Any,
    tenant_id: int,
    project_id: int,
    dataset_code: str,
    dataset_name: str,
    role_code: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT dataset_id, dataset_role_code
            FROM catalog.dataset
            WHERE tenant_id = %s
              AND project_id = %s
              AND dataset_code = %s
            FOR UPDATE;
            """,
            (tenant_id, project_id, dataset_code),
        )
        existing = cursor.fetchone()
        if existing:
            if existing[1] != role_code:
                raise ValueError(
                    f"Dataset {dataset_code} exists with role {existing[1]}."
                )
            return int(existing[0])

        cursor.execute(
            """
            INSERT INTO catalog.dataset (
                tenant_id,
                project_id,
                dataset_code,
                dataset_name,
                object_type_code,
                dataset_role_code,
                layer_code,
                status_code
            )
            VALUES (%s, %s, %s, %s, 'TABLE', %s, %s, 'ACTIVE')
            RETURNING dataset_id;
            """,
            (
                tenant_id,
                project_id,
                dataset_code,
                dataset_name,
                role_code,
                "SOURCE" if role_code == "SOURCE" else "CURATED",
            ),
        )
        return int(cursor.fetchone()[0])


def ensure_binding(
    connection: Any,
    tenant_id: int,
    environment_id: int,
    dataset_id: int,
    connection_id: int,
    catalog_name: str,
    schema_name: str,
    object_name: str,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                dataset_binding_id,
                connection_id,
                catalog_name,
                schema_name,
                object_name,
                status_code
            FROM catalog.dataset_binding
            WHERE dataset_id = %s
              AND environment_id = %s
            FOR UPDATE;
            """,
            (dataset_id, environment_id),
        )
        existing = cursor.fetchone()
        expected = (
            connection_id,
            catalog_name,
            schema_name,
            object_name,
            "ACTIVE",
        )
        if existing:
            if tuple(existing[1:]) != expected:
                raise ValueError(
                    f"Dataset binding {existing[0]} conflicts with the "
                    f"requested physical object {catalog_name}.{schema_name}.{object_name}."
                )
            return int(existing[0])

        cursor.execute(
            """
            INSERT INTO catalog.dataset_binding (
                tenant_id,
                dataset_id,
                environment_id,
                connection_id,
                catalog_name,
                schema_name,
                object_name,
                object_name_normalized,
                status_code
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE')
            RETURNING dataset_binding_id;
            """,
            (
                tenant_id,
                dataset_id,
                environment_id,
                connection_id,
                catalog_name,
                schema_name,
                object_name,
                object_name.lower(),
            ),
        )
        return int(cursor.fetchone()[0])


def register_catalog_bindings(
    source_profile: dict[str, Any],
    target_profile: dict[str, Any],
) -> None:
    with get_metastore_connection() as connection:
        try:
            tenant_id = source_profile["tenant_id"]
            environment_id = source_profile["environment_id"]
            if tenant_id <= 0 or environment_id <= 0:
                raise ValueError("Tenant and environment IDs must be positive.")
            if (
                target_profile["tenant_id"] != tenant_id
                or target_profile["system_id"] != source_profile["system_id"]
                or target_profile["environment_id"] != environment_id
            ):
                raise ValueError(
                    "Source and target profiles must share tenant, system, "
                    "and environment for these bindings."
                )

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT project_id
                    FROM catalog.dataset
                    WHERE tenant_id = %s
                      AND dataset_code = 'CUSTOMER_DATASET'
                    ORDER BY project_id
                    LIMIT 1;
                    """,
                    (tenant_id,),
                )
                project_row = cursor.fetchone()
            if project_row is None:
                raise LookupError(
                    "Could not find the existing Customer project to reuse."
                )
            project_id = int(project_row[0])

            for table in TABLES:
                source_dataset_id = ensure_dataset(
                    connection,
                    tenant_id,
                    project_id,
                    table["source_code"],
                    table["source_name"],
                    "SOURCE",
                )
                target_dataset_id = ensure_dataset(
                    connection,
                    tenant_id,
                    project_id,
                    table["target_code"],
                    table["target_name"],
                    "TARGET",
                )
                source_binding_id = ensure_binding(
                    connection,
                    tenant_id,
                    environment_id,
                    source_dataset_id,
                    SOURCE_CONNECTION_ID,
                    source_profile["database_name"],
                    SOURCE_SCHEMA,
                    table["source_table"],
                )
                target_binding_id = ensure_binding(
                    connection,
                    tenant_id,
                    environment_id,
                    target_dataset_id,
                    TARGET_CONNECTION_ID,
                    target_profile["database_name"],
                    TARGET_SCHEMA,
                    table["target_table"],
                )
                print(
                    f"{table['source_table']}: source dataset/binding "
                    f"{source_dataset_id}/{source_binding_id}; target "
                    f"{target_dataset_id}/{target_binding_id}"
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


def main() -> None:
    ensure_source_username()
    with get_metastore_connection() as connection:
        source_profile, target_profile = get_profiles(connection)
    if source_profile["status_code"] != "ACTIVE":
        raise ValueError("Source connection 18 must be ACTIVE.")
    if target_profile["status_code"] != "ACTIVE":
        raise ValueError("Target connection 11 must be ACTIVE.")
    if source_profile["connection_role_code"] not in ("SOURCE", "BOTH"):
        raise ValueError("Connection 18 must have SOURCE or BOTH role.")
    if target_profile["connection_role_code"] not in ("TARGET", "BOTH"):
        raise ValueError("Connection 11 must have TARGET or BOTH role.")

    add_source_watermarks()
    create_target_tables()
    register_catalog_bindings(source_profile, target_profile)
    print("Incremental append preparation completed.")


if __name__ == "__main__":
    main()