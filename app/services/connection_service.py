"""
Connection Metadata Service
===========================

This service resolves a connection_id from the metadata/control
database into a platform-neutral ConnectionMetadata object.

The service does NOT directly connect to the source database.

Its responsibility is only:

    connection_id
          |
          v
    metadata lookup
          |
          v
    ConnectionMetadata
          |
          v
    ConnectorFactory

The ConnectorFactory will later create the actual database
connector.

This separation is important because the platform must support
multiple database technologies without changing the ingestion
engine.

Supported databases can eventually include:

    PostgreSQL
    MySQL
    SQL Server
    Oracle
    Snowflake
    Databricks
    etc.
"""

from app.db.metastore import get_metastore_connection

from app.models.connection import (
    ConnectionMetadata,
    ConnectionParameter,
)


class ConnectionNotFoundError(Exception):
    """
    Raised when the requested connection does not exist or is
    not active.
    """

    pass


class ConnectionService:
    """
    Service responsible for reading connection metadata from
    the metadata/control database.
    """

    def __init__(self) -> None:
        """
        Initialize the connection service.

        The service does not create a permanent database
        connection.

        A metadata database connection is created only when
        required and is automatically closed afterwards.
        """

        pass

    def get_connection_metadata(
        self,
        connection_id: int,
    ) -> ConnectionMetadata:
        """
        Resolve a connection_id into complete connection metadata.

        Parameters
        ----------
        connection_id:
            Unique identifier from conn.connection_profile.

        Returns
        -------
        ConnectionMetadata
            Complete platform-neutral connection information.

        Raises
        ------
        ValueError
            If connection_id is invalid.

        ConnectionNotFoundError
            If the connection does not exist or is not ACTIVE.
        """

        # =====================================================
        # VALIDATE INPUT
        # =====================================================

        if connection_id <= 0:
            raise ValueError(
                "connection_id must be greater than zero."
            )

        # =====================================================
        # MAIN CONNECTION QUERY
        # =====================================================
        #
        # Relationship:
        #
        # connection_profile
        #       |
        #       | connector_version_id
        #       v
        # connector_version
        #       |
        #       | connector_id
        #       v
        # connector
        #
        # This gives us both connection information and the
        # connector implementation information.
        # =====================================================

        connection_query = """
            SELECT
                cp.connection_id,
                cp.connection_name,

                cp.connector_version_id,
                cp.credential_id,
                cp.connection_role_code,

                cp.host_name,
                cp.port_no,
                cp.database_name,
                cp.endpoint_url,

                cp.connect_timeout_seconds,
                cp.command_timeout_seconds,

                c.connector_id,
                c.connector_code,
                c.connector_name,

                cv.semantic_version

            FROM conn.connection_profile AS cp

            INNER JOIN conn.connector_version AS cv
                ON cv.connector_version_id =
                   cp.connector_version_id

            INNER JOIN conn.connector AS c
                ON c.connector_id =
                   cv.connector_id

            WHERE cp.connection_id = %s

              AND cp.status_code = 'ACTIVE'

              AND cv.status_code = 'ACTIVE'

              AND c.status_code = 'ACTIVE'

            LIMIT 1;
        """

        # =====================================================
        # CONNECTION PARAMETERS QUERY
        # =====================================================
        #
        # Parameters are stored separately from the main
        # connection profile.
        #
        # Example:
        #
        # username = postgres
        #
        # Later this can contain database-specific parameters:
        #
        # schema
        # warehouse
        # role
        # service_name
        # authentication_mode
        # etc.
        # =====================================================

        parameter_query = """
            SELECT
                parameter_name,
                parameter_value,
                value_type_code,
                is_secret_ref

            FROM conn.connection_parameter

            WHERE connection_id = %s

            ORDER BY connection_parameter_id;
        """

        # =====================================================
        # READ METADATA DATABASE
        # =====================================================

        with get_metastore_connection() as connection:

            with connection.cursor() as cursor:

                # -------------------------------------------------
                # Retrieve main connection metadata.
                # -------------------------------------------------

                cursor.execute(
                    connection_query,
                    (connection_id,),
                )

                row = cursor.fetchone()

                # -------------------------------------------------
                # No active connection was found.
                # -------------------------------------------------

                if row is None:

                    raise ConnectionNotFoundError(
                        f"Connection ID {connection_id} "
                        "was not found or is not ACTIVE."
                    )

                # -------------------------------------------------
                # Map query result to meaningful variables.
                # -------------------------------------------------

                (
                    resolved_connection_id,
                    connection_name,

                    connector_version_id,
                    credential_id,
                    connection_role_code,

                    host_name,
                    port_no,
                    database_name,
                    endpoint_url,

                    connect_timeout_seconds,
                    command_timeout_seconds,

                    connector_id,
                    connector_code,
                    connector_name,

                    connector_version,
                ) = row

                # -------------------------------------------------
                # Retrieve dynamic parameters.
                # -------------------------------------------------

                cursor.execute(
                    parameter_query,
                    (resolved_connection_id,),
                )

                parameters: dict[
                    str,
                    ConnectionParameter
                ] = {}

                for parameter_row in cursor.fetchall():

                    (
                        parameter_name,
                        parameter_value,
                        value_type_code,
                        is_secret_ref,
                    ) = parameter_row

                    # -------------------------------------------------
                    # Normalize parameter names.
                    #
                    # This allows:
                    #
                    # username
                    # USERNAME
                    # UserName
                    #
                    # to be handled consistently.
                    # -------------------------------------------------

                    normalized_name = (
                        parameter_name
                        .strip()
                        .lower()
                    )

                    parameters[
                        normalized_name
                    ] = ConnectionParameter(
                        name=normalized_name,
                        value=parameter_value,
                        value_type=value_type_code,
                        is_secret_ref=is_secret_ref,
                    )

        # =====================================================
        # BUILD PLATFORM-NEUTRAL OBJECT
        # =====================================================

        metadata = ConnectionMetadata(

            connection_id=(
                resolved_connection_id
            ),

            connection_name=(
                connection_name
            ),

            connector_id=(
                connector_id
            ),

            connector_code=(
                connector_code
            ),

            connector_name=(
                connector_name
            ),

            connector_version_id=(
                connector_version_id
            ),

            connector_version=(
                connector_version
            ),

            host_name=(
                host_name
            ),

            port_no=(
                port_no
            ),

            database_name=(
                database_name
            ),

            endpoint_url=(
                endpoint_url
            ),

            credential_id=(
                credential_id
            ),

            connection_role_code=(
                connection_role_code
            ),

            connect_timeout_seconds=(
                connect_timeout_seconds
            ),

            command_timeout_seconds=(
                command_timeout_seconds
            ),

            parameters=(
                parameters
            ),
        )

        return metadata