"""
Create the TARGET connection profile for the ingestion platform.

WHY THIS SCRIPT EXISTS
----------------------
The ingestion platform needs separate logical SOURCE and TARGET
connection profiles.

SOURCE:

    connection_id = 1
    role          = SOURCE
    database      = demo_source_db

TARGET:

    connection_id = new ID
    role          = TARGET
    database      = ingestion_metastore

The target connection is stored in the metadata/control database.

IMPORTANT
---------
The password is NOT stored in this script.

Instead:

    connection_profile.credential_id
                    |
                    v
             credential_ref
                    |
                    v
              secret provider
                    |
                    v
                 secret

This keeps credentials separated from connection metadata.

TRANSACTION DESIGN
------------------
This script explicitly controls the transaction.

The complete operation is:

    BEGIN
      |
      +-- Validate connector
      |
      +-- Validate credential
      |
      +-- Create connection_profile
      |
      +-- Create connection_parameter
      |
      +-- Verify inserted metadata
      |
      +-- COMMIT
      |
      +-- If anything fails -> ROLLBACK

This prevents partially-created target connections.
"""

from app.db.metastore import get_metastore_connection


# ============================================================================
# TARGET CONNECTION METADATA
# ============================================================================

# Logical name of the TARGET connection.
#
# This is different from the SOURCE connection name so that the metadata
# store can distinguish the two connection profiles.
TARGET_CONNECTION_NAME = "Demo PostgreSQL Target Connection"


# These identify the tenant/system/environment to which the connection
# belongs.
#
# We obtained these values from the existing Demo PostgreSQL SOURCE
# connection after inspecting the actual metadata.
TENANT_ID = 1
SYSTEM_ID = 1
ENVIRONMENT_ID = 1


# Connector version 3 represents:
#
# connector_id       = 3
# connector_code     = POSTGRESQL_CONNECTOR
# semantic_version   = 1.0.0
#
# This is the Python/libpq PostgreSQL connector that our application
# currently implements.
CONNECTOR_VERSION_ID = 3


# Credential reference used by the PostgreSQL connection.
#
# IMPORTANT:
# This is only a reference ID.
# The actual password is NOT stored here.
CREDENTIAL_ID = 1


# PostgreSQL target connection details.
TARGET_ROLE = "TARGET"

TARGET_HOST = "192.168.11.91"
TARGET_PORT = 5432
TARGET_DATABASE = "ingestion_metastore"


# Endpoint URL is connection metadata.
#
# It does not contain the password.
TARGET_ENDPOINT_URL = (
    "postgresql://192.168.11.91:5432/ingestion_metastore"
)


# Username is stored as a normal connection parameter.
#
# The password remains behind the credential reference.
TARGET_USERNAME = "postgres"


def main() -> None:
    """
    Create the TARGET connection profile.

    The function explicitly manages the database transaction so that:

        SUCCESS -> COMMIT

        FAILURE -> ROLLBACK
    """

    print("=" * 80)
    print("CREATE TARGET CONNECTION")
    print("=" * 80)

    # ------------------------------------------------------------------------
    # Open the metadata database connection.
    #
    # get_metastore_connection() manages the lifecycle of the connection,
    # but it intentionally does NOT automatically commit application
    # transactions.
    #
    # Therefore this function is responsible for commit/rollback.
    # ------------------------------------------------------------------------

    with get_metastore_connection() as connection:

        try:

            # =================================================================
            # STEP 1
            # Check whether the TARGET connection already exists.
            # =================================================================
            #
            # WHY:
            # This makes the script idempotent.
            #
            # If the script is executed again, we don't want to create
            # duplicate target connections.
            # -----------------------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        connection_id,
                        connection_name,
                        connection_role_code,
                        database_name
                    FROM conn.connection_profile
                    WHERE system_id = %s
                      AND environment_id = %s
                      AND connection_role_code = %s
                      AND connection_name = %s;
                    """,
                    (
                        SYSTEM_ID,
                        ENVIRONMENT_ID,
                        TARGET_ROLE,
                        TARGET_CONNECTION_NAME,
                    ),
                )

                existing_connection = cursor.fetchone()

                if existing_connection:

                    print("\nTARGET CONNECTION ALREADY EXISTS")

                    print(
                        f"Connection ID   : {existing_connection[0]}"
                    )

                    print(
                        f"Connection Name : {existing_connection[1]}"
                    )

                    print(
                        f"Role            : {existing_connection[2]}"
                    )

                    print(
                        f"Database        : {existing_connection[3]}"
                    )

                    # Nothing needs to be inserted.
                    #
                    # We explicitly rollback any open transaction because
                    # this execution did not perform a write operation.
                    connection.rollback()

                    return

                # =============================================================
                # STEP 2
                # Validate the connector version.
                # =============================================================
                #
                # WHY:
                # connection_profile.connector_version_id is a foreign key.
                #
                # We also verify:
                #
                #   1. Connector exists
                #   2. Connector version is ACTIVE
                #   3. Connector supports TARGET
                #
                # This prevents invalid runtime configuration.
                # -------------------------------------------------------------

                cursor.execute(
                    """
                    SELECT
                        cv.connector_version_id,
                        c.connector_id,
                        c.connector_code,
                        c.connector_name,
                        cv.semantic_version,
                        cv.status_code,
                        c.supports_target
                    FROM conn.connector_version cv
                    JOIN conn.connector c
                        ON cv.connector_id = c.connector_id
                    WHERE cv.connector_version_id = %s;
                    """,
                    (CONNECTOR_VERSION_ID,),
                )

                connector = cursor.fetchone()

                if connector is None:
                    raise RuntimeError(
                        f"Connector version "
                        f"{CONNECTOR_VERSION_ID} does not exist."
                    )

                (
                    connector_version_id,
                    connector_id,
                    connector_code,
                    connector_name,
                    semantic_version,
                    connector_status,
                    supports_target,
                ) = connector

                # The connector version must be ACTIVE.
                if connector_status != "ACTIVE":
                    raise RuntimeError(
                        f"Connector version "
                        f"{connector_version_id} is not ACTIVE."
                    )

                # The connector must support TARGET operations.
                if not supports_target:
                    raise RuntimeError(
                        f"Connector {connector_code} "
                        f"does not support TARGET operations."
                    )

                print("\nConnector validated:")
                print(
                    f"Connector ID      : {connector_id}"
                )
                print(
                    f"Connector Code    : {connector_code}"
                )
                print(
                    f"Connector Name    : {connector_name}"
                )
                print(
                    f"Semantic Version  : {semantic_version}"
                )
                print(
                    f"Target Supported  : {supports_target}"
                )

                # =============================================================
                # STEP 3
                # Validate the credential reference.
                # =============================================================
                #
                # WHY:
                # The target connection should reference an existing
                # credential rather than storing a password directly.
                #
                # We only validate the metadata reference.
                # We never print the actual secret.
                # -------------------------------------------------------------

                cursor.execute(
                    """
                    SELECT
                        credential_id,
                        credential_name,
                        secret_provider_code
                    FROM conn.credential_ref
                    WHERE credential_id = %s;
                    """,
                    (CREDENTIAL_ID,),
                )

                credential = cursor.fetchone()

                if credential is None:
                    raise RuntimeError(
                        f"Credential reference "
                        f"{CREDENTIAL_ID} does not exist."
                    )

                (
                    credential_id,
                    credential_name,
                    secret_provider_code,
                ) = credential

                print("\nCredential reference validated:")
                print(
                    f"Credential ID : {credential_id}"
                )
                print(
                    f"Credential     : {credential_name}"
                )
                print(
                    f"Provider       : {secret_provider_code}"
                )

                # =============================================================
                # STEP 4
                # Create the TARGET connection profile.
                # =============================================================
                #
                # WHY:
                # This creates the logical target endpoint in the metadata
                # store.
                #
                # Notice:
                #
                #     credential_id
                #
                # is stored instead of the password.
                # -------------------------------------------------------------

                cursor.execute(
                    """
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
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    )
                    RETURNING connection_id;
                    """,
                    (
                        TENANT_ID,
                        SYSTEM_ID,
                        ENVIRONMENT_ID,
                        CONNECTOR_VERSION_ID,
                        CREDENTIAL_ID,
                        TARGET_ROLE,
                        TARGET_CONNECTION_NAME,
                        TARGET_HOST,
                        TARGET_PORT,
                        TARGET_DATABASE,
                        TARGET_ENDPOINT_URL,
                        30,
                        600,
                        "ACTIVE",
                    ),
                )

                target_connection_id = cursor.fetchone()[0]

                print("\nTARGET CONNECTION CREATED")
                print(
                    f"Connection ID : {target_connection_id}"
                )

                # =============================================================
                # STEP 5
                # Create the username connection parameter.
                # =============================================================
                #
                # WHY:
                # The platform stores dynamic connection parameters separately
                # from the main connection profile.
                #
                # Username is a normal STRING parameter.
                #
                # Password is deliberately NOT inserted here.
                # -------------------------------------------------------------

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
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        %s
                    );
                    """,
                    (
                        target_connection_id,
                        "username",
                        TARGET_USERNAME,
                        "STRING",
                        False,
                        False,
                    ),
                )

                print("Username parameter created.")

                # =============================================================
                # STEP 6
                # Verify the newly-created connection.
                # =============================================================
                #
                # WHY:
                # We don't want to commit based only on the INSERT result.
                #
                # We read the metadata back and verify the important fields.
                # -------------------------------------------------------------

                cursor.execute(
                    """
                    SELECT
                        connection_id,
                        connection_name,
                        connection_role_code,
                        connector_version_id,
                        credential_id,
                        host_name,
                        port_no,
                        database_name,
                        status_code
                    FROM conn.connection_profile
                    WHERE connection_id = %s;
                    """,
                    (target_connection_id,),
                )

                created_connection = cursor.fetchone()

                if created_connection is None:
                    raise RuntimeError(
                        "Target connection was inserted but "
                        "could not be read back."
                    )

                (
                    connection_id,
                    connection_name,
                    role,
                    connector_version,
                    credential_id,
                    host,
                    port,
                    database,
                    status,
                ) = created_connection

                print("\nTARGET CONNECTION VERIFICATION")
                print(
                    f"Connection ID      : {connection_id}"
                )
                print(
                    f"Connection Name    : {connection_name}"
                )
                print(
                    f"Role               : {role}"
                )
                print(
                    f"Connector Version  : {connector_version}"
                )
                print(
                    f"Credential ID      : {credential_id}"
                )
                print(
                    f"Host               : {host}"
                )
                print(
                    f"Port               : {port}"
                )
                print(
                    f"Database           : {database}"
                )
                print(
                    f"Status             : {status}"
                )

                # Validate the role.
                if role != "TARGET":
                    raise RuntimeError(
                        "Created connection does not have TARGET role."
                    )

                # Validate the target database.
                if database != TARGET_DATABASE:
                    raise RuntimeError(
                        "Created target connection points to "
                        "an unexpected database."
                    )

            # =================================================================
            # STEP 7
            # COMMIT THE COMPLETE TRANSACTION.
            # =================================================================
            #
            # WHY:
            # psycopg starts a transaction when SQL statements modify data.
            #
            # Our metastore connection manager only closes the connection;
            # it does not automatically commit this application-level write.
            #
            # Therefore we explicitly commit only after all validation
            # steps have succeeded.
            # =================================================================

            connection.commit()

            print("\nTRANSACTION COMMITTED")

        except Exception:

            # =================================================================
            # ROLLBACK
            # =================================================================
            #
            # WHY:
            # If ANY operation fails, we don't want partial metadata.
            #
            # For example, imagine:
            #
            #     connection_profile INSERT -> SUCCESS
            #     connection_parameter INSERT -> FAILURE
            #
            # Without rollback, we could end up with an incomplete target
            # connection.
            #
            # Rollback restores the metadata database to its previous state.
            # =================================================================

            connection.rollback()

            print("\nTRANSACTION ROLLED BACK")

            # Re-raise the original exception so the command line clearly
            # reports the actual failure.
            raise

    print("\n" + "=" * 80)
    print("TARGET CONNECTION CREATION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()