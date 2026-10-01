"""
Inspect Source Connection Mapping
=================================

This script compares the existing ingestion source configuration
with the newer conn.connection_profile model.

WHY THIS IS REQUIRED
--------------------
We have discovered two connection architectures:

    1. conn.connection_profile
    2. ingest.connection_config

Both source_config and target_config currently reference
ingest.connection_config.

Before implementing the ingestion runtime, we need to understand
whether the source metadata and the newer connection metadata
describe the same physical database.

This script is READ-ONLY.

It does not modify any database records.
"""


from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Current POC source configuration.
# ---------------------------------------------------------------------------
SOURCE_ID = 1


def main() -> None:
    """
    Compare the source configuration with both connection models.
    """

    print("=" * 80)
    print("INSPECT SOURCE CONNECTION MAPPING")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # =================================================================
            # STEP 1
            # Read the source configuration.
            # =================================================================

            cursor.execute(
                """
                SELECT
                    source_id,
                    connection_id,
                    source_name,
                    source_type,
                    database_name,
                    schema_name,
                    object_name,
                    is_active
                FROM ingest.source_config
                WHERE source_id = %s;
                """,
                (SOURCE_ID,),
            )

            source_config = cursor.fetchone()

            if source_config is None:
                raise RuntimeError(
                    f"Source configuration {SOURCE_ID} "
                    "does not exist."
                )

            (
                source_id,
                ingest_connection_id,
                source_name,
                source_type,
                source_database,
                source_schema,
                source_object,
                source_active,
            ) = source_config

            print()
            print("INGEST SOURCE CONFIGURATION")
            print("-" * 80)
            print(f"Source ID          : {source_id}")
            print(f"Ingest Connection ID: {ingest_connection_id}")
            print(f"Source Name        : {source_name}")
            print(f"Source Type        : {source_type}")
            print(f"Database           : {source_database}")
            print(f"Schema             : {source_schema}")
            print(f"Object             : {source_object}")
            print(f"Active             : {source_active}")

            # =================================================================
            # STEP 2
            # Read the connection_config referenced by source_config.
            # =================================================================

            cursor.execute(
                """
                SELECT
                    connection_id,
                    connection_name,
                    connection_type,
                    host,
                    port,
                    database_name,
                    username,
                    credential_ref,
                    is_active
                FROM ingest.connection_config
                WHERE connection_id = %s;
                """,
                (ingest_connection_id,),
            )

            ingest_connection = cursor.fetchone()

            if ingest_connection is None:
                raise RuntimeError(
                    f"ingest.connection_config "
                    f"connection {ingest_connection_id} "
                    "does not exist."
                )

            (
                connection_id,
                connection_name,
                connection_type,
                host,
                port,
                database_name,
                username,
                credential_ref,
                connection_active,
            ) = ingest_connection

            print()
            print("INGEST CONNECTION CONFIGURATION")
            print("-" * 80)
            print(f"Connection ID      : {connection_id}")
            print(f"Connection Name    : {connection_name}")
            print(f"Connection Type    : {connection_type}")
            print(f"Host               : {host}")
            print(f"Port               : {port}")
            print(f"Database           : {database_name}")
            print(f"Username           : {username}")
            print(f"Credential Ref     : {credential_ref}")
            print(f"Active             : {connection_active}")

            # =================================================================
            # STEP 3
            # Read the corresponding newer conn.connection_profile record.
            #
            # We deliberately use the SAME numeric ID only for comparison.
            # We are NOT assuming that the IDs represent the same object.
            # =================================================================

            cursor.execute(
                """
                SELECT
                    connection_id,
                    connection_name,
                    connection_role_code,
                    host_name,
                    port_no,
                    database_name,
                    credential_id,
                    status_code
                FROM conn.connection_profile
                WHERE connection_id = %s;
                """,
                (ingest_connection_id,),
            )

            conn_connection = cursor.fetchone()

            print()
            print("NEW CONNECTION MODEL")
            print("-" * 80)

            if conn_connection is None:

                print(
                    f"No conn.connection_profile record exists "
                    f"with connection_id = {ingest_connection_id}."
                )

            else:

                (
                    new_connection_id,
                    new_connection_name,
                    connection_role,
                    new_host,
                    new_port,
                    new_database,
                    credential_id,
                    status_code,
                ) = conn_connection

                print(
                    f"Connection ID      : {new_connection_id}"
                )
                print(
                    f"Connection Name    : {new_connection_name}"
                )
                print(
                    f"Role               : {connection_role}"
                )
                print(
                    f"Host               : {new_host}"
                )
                print(
                    f"Port               : {new_port}"
                )
                print(
                    f"Database           : {new_database}"
                )
                print(
                    f"Credential ID      : {credential_id}"
                )
                print(
                    f"Status             : {status_code}"
                )

            # =================================================================
            # STEP 4
            # Display the architectural comparison.
            # =================================================================

            print()
            print("COMPARISON")
            print("-" * 80)

            print(
                f"Ingest source connection ID : "
                f"{ingest_connection_id}"
            )

            print(
                f"Ingest connection database  : "
                f"{database_name}"
            )

            print(
                f"Source config database      : "
                f"{source_database}"
            )

            if conn_connection is not None:

                print(
                    f"New conn database           : "
                    f"{new_database}"
                )

                print(
                    f"New conn host               : "
                    f"{new_host}"
                )

                print(
                    f"New conn port               : "
                    f"{new_port}"
                )

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()