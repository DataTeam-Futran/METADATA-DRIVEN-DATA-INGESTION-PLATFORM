"""
Update Target Configuration
===========================

This script updates the logical target configuration so that it
uses the correct physical TARGET connection.

Architecture:

    ingest.target_config
            |
            | connection_id
            v
    conn.connection_profile
            |
            v
    PostgreSQL Target Database


CURRENT POC
-----------

Logical target:

    target_id      = 1
    target_name    = EMPLOYEE_TARGET

Physical target connection:

    connection_id  = 11
    role           = TARGET
    database       = ingestion_metastore


IMPORTANT
---------

The metadata connection manager does NOT automatically commit
transactions.

Therefore this script explicitly handles:

    connection.commit()

on success, and:

    connection.rollback()

on failure.

This prevents partially completed metadata updates.
"""

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Existing logical target configuration.
#
# This record already exists in ingest.target_config.
# ---------------------------------------------------------------------------
TARGET_ID = 1


# ---------------------------------------------------------------------------
# Newly created physical target connection.
#
# This connection was created successfully by:
#
#     scripts.create_target_connection
#
# and persisted with connection_id = 11.
# ---------------------------------------------------------------------------
TARGET_CONNECTION_ID = 11


def main() -> None:
    """
    Update ingest.target_config so target_id=1 uses
    connection_id=11.

    The function validates the target connection first and then
    updates only the connection reference.
    """

    print("=" * 80)
    print("UPDATE TARGET CONFIGURATION")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # Open a metadata database connection.
    #
    # This connection is used to read and update metadata tables.
    # -----------------------------------------------------------------------
    with get_metastore_connection() as connection:

        try:

            # =================================================================
            # STEP 1
            # Validate the target connection.
            # =================================================================
            #
            # Before changing target_config, make sure the referenced
            # connection actually exists and is usable as a TARGET.
            #
            # =================================================================
            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        connection_id,
                        connection_name,
                        connection_role_code,
                        database_name,
                        status_code
                    FROM conn.connection_profile
                    WHERE connection_id = %s;
                    """,
                    (TARGET_CONNECTION_ID,),
                )

                target_connection = cursor.fetchone()

                # ------------------------------------------------------------
                # The connection must exist.
                # ------------------------------------------------------------
                if target_connection is None:
                    raise RuntimeError(
                        f"Target connection {TARGET_CONNECTION_ID} "
                        "does not exist."
                    )

                (
                    connection_id,
                    connection_name,
                    connection_role,
                    database_name,
                    status_code,
                ) = target_connection

                # ------------------------------------------------------------
                # A TARGET or BOTH connection is required.
                #
                # SOURCE-only connections must never be used for target
                # loading.
                # ------------------------------------------------------------
                if connection_role not in ("TARGET", "BOTH"):
                    raise RuntimeError(
                        f"Connection {connection_id} has role "
                        f"{connection_role}. "
                        "Expected TARGET or BOTH."
                    )

                # ------------------------------------------------------------
                # Only ACTIVE connections should be used by the runtime.
                # ------------------------------------------------------------
                if status_code != "ACTIVE":
                    raise RuntimeError(
                        f"Target connection {connection_id} is "
                        f"not ACTIVE. Current status: {status_code}"
                    )

                print()
                print("TARGET CONNECTION VALIDATED")
                print(f"Connection ID   : {connection_id}")
                print(f"Connection Name : {connection_name}")
                print(f"Role            : {connection_role}")
                print(f"Database        : {database_name}")
                print(f"Status          : {status_code}")

                # =================================================================
                # STEP 2
                # Read the existing target configuration.
                # =================================================================
                #
                # We use the ACTUAL column names discovered from the database:
                #
                #     target_database
                #     target_schema
                #     target_object
                #
                # We do NOT assume generic names such as database_name.
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
                    (TARGET_ID,),
                )

                target_config = cursor.fetchone()

                # ------------------------------------------------------------
                # The logical target must exist before we update it.
                # ------------------------------------------------------------
                if target_config is None:
                    raise RuntimeError(
                        f"Target configuration {TARGET_ID} "
                        "does not exist."
                    )

                (
                    target_id,
                    old_connection_id,
                    target_name,
                    target_type,
                    target_database,
                    target_schema,
                    target_object,
                    is_active,
                ) = target_config

                print()
                print("CURRENT TARGET CONFIGURATION")
                print(f"Target ID       : {target_id}")
                print(f"Target Name     : {target_name}")
                print(f"Old Connection  : {old_connection_id}")
                print(f"Target Type     : {target_type}")
                print(f"Target Database : {target_database}")
                print(f"Target Schema   : {target_schema}")
                print(f"Target Object   : {target_object}")
                print(f"Active          : {is_active}")

                # =================================================================
                # STEP 3
                # Update ONLY the physical connection reference.
                # =================================================================
                #
                # We intentionally do not modify:
                #
                #     target_name
                #     target_type
                #     target_database
                #     target_schema
                #     target_object
                #
                # Those values already correctly describe the logical target.
                #
                # Only this relationship changes:
                #
                #     connection_id = 1
                #
                # to:
                #
                #     connection_id = 11
                #
                # =================================================================

                cursor.execute(
                    """
                    UPDATE ingest.target_config
                    SET
                        connection_id = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE target_id = %s;
                    """,
                    (
                        TARGET_CONNECTION_ID,
                        TARGET_ID,
                    ),
                )

                # ------------------------------------------------------------
                # Confirm that PostgreSQL actually updated one row.
                # ------------------------------------------------------------
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Expected exactly one target configuration "
                        f"to be updated, but {cursor.rowcount} rows "
                        "were affected."
                    )

                # =================================================================
                # STEP 4
                # Verify the updated metadata before committing.
                # =================================================================
                #
                # This protects us from committing an unexpected state.
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
                    (TARGET_ID,),
                )

                updated_config = cursor.fetchone()

                if updated_config is None:
                    raise RuntimeError(
                        "Target configuration could not be found "
                        "after the update."
                    )

                (
                    verified_target_id,
                    verified_connection_id,
                    verified_target_name,
                    verified_target_type,
                    verified_database,
                    verified_schema,
                    verified_object,
                    verified_active,
                ) = updated_config

                # ------------------------------------------------------------
                # Confirm that the connection reference is now 11.
                # ------------------------------------------------------------
                if verified_connection_id != TARGET_CONNECTION_ID:
                    raise RuntimeError(
                        "Target configuration verification failed. "
                        f"Expected connection {TARGET_CONNECTION_ID}, "
                        f"but found {verified_connection_id}."
                    )

                print()
                print("UPDATED TARGET CONFIGURATION")
                print(f"Target ID       : {verified_target_id}")
                print(f"Target Name     : {verified_target_name}")
                print(f"Target Type     : {verified_target_type}")
                print(f"Connection ID   : {verified_connection_id}")
                print(f"Target Database : {verified_database}")
                print(f"Target Schema   : {verified_schema}")
                print(f"Target Object   : {verified_object}")
                print(f"Active          : {verified_active}")

            # =================================================================
            # STEP 5
            # Commit the transaction.
            # =================================================================
            #
            # Without this explicit commit, PostgreSQL would roll back the
            # UPDATE when the connection closes.
            # =================================================================

            connection.commit()

            print()
            print("TRANSACTION COMMITTED")

        except Exception:

            # =================================================================
            # STEP 6
            # Roll back if anything fails.
            # =================================================================
            #
            # This guarantees that a failed metadata update does not leave
            # the target configuration in a partially modified state.
            # =================================================================

            connection.rollback()

            print()
            print("TRANSACTION ROLLED BACK")

            # Re-raise the original exception so the script exits with
            # a failure status and the actual problem remains visible.
            raise

    print()
    print("=" * 80)
    print("TARGET CONFIGURATION UPDATE COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()