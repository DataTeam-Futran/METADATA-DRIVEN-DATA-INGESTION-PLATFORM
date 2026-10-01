"""
Inspect POC Execution Chain
===========================

This script traces the metadata used by the current published
full-load mapping.

Current POC:

    mapping_version_id = 1

The script follows this metadata chain:

    mapping_version
          |
          v
       mapping
          |
          v
       dataset
       /     \
      /       \
 source       target
   |             |
   v             v
source_config  target_config
   |             |
   └──────┬──────┘
          v
   connection_config

WHY THIS SCRIPT EXISTS
----------------------
Before implementing the actual ingestion runtime, we need to
understand exactly which metadata records participate in the
current POC.

IMPORTANT
---------
This script is READ-ONLY.

It does not INSERT, UPDATE, DELETE, or ALTER any metadata.

All column names in this script are based on the actual schemas
already inspected in PostgreSQL.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Published mapping version used by the current POC.
# ---------------------------------------------------------------------------
MAPPING_VERSION_ID = 1


def main() -> None:
    """
    Trace the current published mapping version through its
    dataset, source, target, and connection metadata.
    """

    print("=" * 80)
    print("INSPECT POC EXECUTION CHAIN")
    print("=" * 80)

    with get_metastore_connection() as connection:

        with connection.cursor() as cursor:

            # =================================================================
            # STEP 1
            # Resolve the mapping version.
            # =================================================================
            #
            # Actual columns verified from ingest.mapping_version:
            #
            #     mapping_version_id
            #     mapping_id
            #     source_schema_version_id
            #     target_schema_version_id
            #     version_number
            #     status
            #     config_hash
            #
            # =================================================================

            cursor.execute(
                """
                SELECT
                    mv.mapping_version_id,
                    mv.mapping_id,
                    mv.source_schema_version_id,
                    mv.target_schema_version_id,
                    mv.version_number,
                    mv.status,
                    mv.config_hash
                FROM ingest.mapping_version AS mv
                WHERE mv.mapping_version_id = %s;
                """,
                (MAPPING_VERSION_ID,),
            )

            mapping_version = cursor.fetchone()

            if mapping_version is None:
                raise RuntimeError(
                    f"Mapping version {MAPPING_VERSION_ID} "
                    "was not found."
                )

            (
                mapping_version_id,
                mapping_id,
                source_schema_version_id,
                target_schema_version_id,
                version_number,
                status,
                config_hash,
            ) = mapping_version

            print()
            print("MAPPING VERSION")
            print("-" * 80)
            print(
                f"Mapping Version ID       : "
                f"{mapping_version_id}"
            )
            print(
                f"Mapping ID               : "
                f"{mapping_id}"
            )
            print(
                f"Source Schema Version ID : "
                f"{source_schema_version_id}"
            )
            print(
                f"Target Schema Version ID : "
                f"{target_schema_version_id}"
            )
            print(
                f"Version Number           : "
                f"{version_number}"
            )
            print(
                f"Status                   : "
                f"{status}"
            )
            print(
                f"Config Hash              : "
                f"{config_hash}"
            )

            # =================================================================
            # STEP 2
            # Resolve the logical mapping.
            # =================================================================
            #
            # We use the actual mapping columns established earlier:
            #
            #     mapping_id
            #     mapping_name
            #     dataset_id
            #     description
            #     is_active
            #
            # =================================================================

            cursor.execute(
                """
                SELECT
                    mapping_id,
                    mapping_name,
                    dataset_id,
                    description,
                    is_active
                FROM ingest.mapping
                WHERE mapping_id = %s;
                """,
                (mapping_id,),
            )

            mapping = cursor.fetchone()

            if mapping is None:
                raise RuntimeError(
                    f"Mapping {mapping_id} was not found."
                )

            (
                resolved_mapping_id,
                mapping_name,
                dataset_id,
                mapping_description,
                mapping_active,
            ) = mapping

            print()
            print("MAPPING")
            print("-" * 80)
            print(
                f"Mapping ID     : "
                f"{resolved_mapping_id}"
            )
            print(
                f"Mapping Name   : "
                f"{mapping_name}"
            )
            print(
                f"Dataset ID     : "
                f"{dataset_id}"
            )
            print(
                f"Description    : "
                f"{mapping_description}"
            )
            print(
                f"Active         : "
                f"{mapping_active}"
            )

            # =================================================================
            # STEP 3
            # Resolve the dataset.
            # =================================================================
            #
            # The dataset connects the logical source and target.
            # =================================================================

            cursor.execute(
                """
                SELECT
                    dataset_id,
                    dataset_name,
                    source_id,
                    target_id,
                    is_active
                FROM ingest.dataset
                WHERE dataset_id = %s;
                """,
                (dataset_id,),
            )

            dataset = cursor.fetchone()

            if dataset is None:
                raise RuntimeError(
                    f"Dataset {dataset_id} was not found."
                )

            (
                resolved_dataset_id,
                dataset_name,
                source_id,
                target_id,
                dataset_active,
            ) = dataset

            print()
            print("DATASET")
            print("-" * 80)
            print(
                f"Dataset ID     : "
                f"{resolved_dataset_id}"
            )
            print(
                f"Dataset Name   : "
                f"{dataset_name}"
            )
            print(
                f"Source ID      : "
                f"{source_id}"
            )
            print(
                f"Target ID      : "
                f"{target_id}"
            )
            print(
                f"Active         : "
                f"{dataset_active}"
            )

            # =================================================================
            # STEP 4
            # Resolve the source configuration.
            # =================================================================
            #
            # Actual source_config columns verified earlier:
            #
            #     source_id
            #     connection_id
            #     source_name
            #     source_type
            #     source_database
            #     source_schema
            #     source_object
            #
            # =================================================================

            cursor.execute(
                """
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
                WHERE source_id = %s;
                """,
                (source_id,),
            )

            source = cursor.fetchone()

            if source is None:
                raise RuntimeError(
                    f"Source {source_id} was not found."
                )

            (
                resolved_source_id,
                source_connection_id,
                source_name,
                source_type,
                source_database,
                source_schema,
                source_object,
                source_active,
            ) = source

            print()
            print("SOURCE CONFIGURATION")
            print("-" * 80)
            print(
                f"Source ID       : "
                f"{resolved_source_id}"
            )
            print(
                f"Connection ID   : "
                f"{source_connection_id}"
            )
            print(
                f"Source Name     : "
                f"{source_name}"
            )
            print(
                f"Source Type     : "
                f"{source_type}"
            )
            print(
                f"Database        : "
                f"{source_database}"
            )
            print(
                f"Schema          : "
                f"{source_schema}"
            )
            print(
                f"Object          : "
                f"{source_object}"
            )
            print(
                f"Active          : "
                f"{source_active}"
            )

            # =================================================================
            # STEP 5
            # Resolve the target configuration.
            # =================================================================
            #
            # Actual target_config columns verified earlier:
            #
            #     target_id
            #     connection_id
            #     target_name
            #     target_type
            #     target_database
            #     target_schema
            #     target_object
            #     is_active
            #
            # =================================================================

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
                WHERE target_id = %s;
                """,
                (target_id,),
            )

            target = cursor.fetchone()

            if target is None:
                raise RuntimeError(
                    f"Target {target_id} was not found."
                )

            (
                resolved_target_id,
                target_connection_id,
                target_name,
                target_type,
                target_database,
                target_schema,
                target_object,
                target_active,
            ) = target

            print()
            print("TARGET CONFIGURATION")
            print("-" * 80)
            print(
                f"Target ID       : "
                f"{resolved_target_id}"
            )
            print(
                f"Connection ID   : "
                f"{target_connection_id}"
            )
            print(
                f"Target Name     : "
                f"{target_name}"
            )
            print(
                f"Target Type     : "
                f"{target_type}"
            )
            print(
                f"Database        : "
                f"{target_database}"
            )
            print(
                f"Schema          : "
                f"{target_schema}"
            )
            print(
                f"Object          : "
                f"{target_object}"
            )
            print(
                f"Active          : "
                f"{target_active}"
            )

            # =================================================================
            # STEP 6
            # Resolve the source-side ingest connection.
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
                (source_connection_id,),
            )

            source_connection = cursor.fetchone()

            print()
            print("SOURCE INGEST CONNECTION")
            print("-" * 80)

            if source_connection is None:

                print(
                    f"Connection {source_connection_id} "
                    "was not found."
                )

            else:

                (
                    source_conn_id,
                    source_conn_name,
                    source_conn_type,
                    source_conn_host,
                    source_conn_port,
                    source_conn_database,
                    source_conn_username,
                    source_conn_credential_ref,
                    source_conn_active,
                ) = source_connection

                print(
                    f"Connection ID   : "
                    f"{source_conn_id}"
                )
                print(
                    f"Connection Name : "
                    f"{source_conn_name}"
                )
                print(
                    f"Connection Type : "
                    f"{source_conn_type}"
                )
                print(
                    f"Host            : "
                    f"{source_conn_host}"
                )
                print(
                    f"Port            : "
                    f"{source_conn_port}"
                )
                print(
                    f"Database        : "
                    f"{source_conn_database}"
                )
                print(
                    f"Username        : "
                    f"{source_conn_username}"
                )
                print(
                    f"Credential Ref  : "
                    f"{source_conn_credential_ref}"
                )
                print(
                    f"Active          : "
                    f"{source_conn_active}"
                )

            # =================================================================
            # STEP 7
            # Resolve the target-side ingest connection.
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
                (target_connection_id,),
            )

            target_connection = cursor.fetchone()

            print()
            print("TARGET INGEST CONNECTION")
            print("-" * 80)

            if target_connection is None:

                print(
                    f"Connection {target_connection_id} "
                    "was not found."
                )

            else:

                (
                    target_conn_id,
                    target_conn_name,
                    target_conn_type,
                    target_conn_host,
                    target_conn_port,
                    target_conn_database,
                    target_conn_username,
                    target_conn_credential_ref,
                    target_conn_active,
                ) = target_connection

                print(
                    f"Connection ID   : "
                    f"{target_conn_id}"
                )
                print(
                    f"Connection Name : "
                    f"{target_conn_name}"
                )
                print(
                    f"Connection Type : "
                    f"{target_conn_type}"
                )
                print(
                    f"Host            : "
                    f"{target_conn_host}"
                )
                print(
                    f"Port            : "
                    f"{target_conn_port}"
                )
                print(
                    f"Database        : "
                    f"{target_conn_database}"
                )
                print(
                    f"Username        : "
                    f"{target_conn_username}"
                )
                print(
                    f"Credential Ref  : "
                    f"{target_conn_credential_ref}"
                )
                print(
                    f"Active          : "
                    f"{target_conn_active}"
                )

            # =================================================================
            # STEP 8
            # Print the complete execution-chain summary.
            # =================================================================

            print()
            print("EXECUTION CHAIN SUMMARY")
            print("-" * 80)

            print(
                f"Mapping Version : "
                f"{mapping_version_id}"
            )

            print(
                f"Mapping         : "
                f"{mapping_name}"
            )

            print(
                f"Dataset         : "
                f"{dataset_name}"
            )

            print(
                f"Source          : "
                f"{source_database}."
                f"{source_schema}."
                f"{source_object}"
            )

            print(
                f"Source Conn ID  : "
                f"{source_connection_id}"
            )

            print(
                f"Target          : "
                f"{target_database}."
                f"{target_schema}."
                f"{target_object}"
            )

            print(
                f"Target Conn ID  : "
                f"{target_connection_id}"
            )

    print()
    print("=" * 80)
    print("INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()