"""
Connection Metadata Models
==========================

This module defines the platform-neutral models used to represent
database connection metadata.

The models are intentionally database-independent.

The same models can represent:

    PostgreSQL
    MySQL
    SQL Server
    Oracle
    Snowflake
    Databricks
    etc.

Database-specific connection logic belongs in the connector
implementation, not in these models.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConnectionParameter:
    """
    Represents one dynamic connection parameter.

    Examples:

        username
        warehouse
        role
        service_name
        schema

    The value can either be a normal configuration value or a
    reference to a secret.
    """

    name: str
    value: Any
    value_type: str
    is_secret_ref: bool


@dataclass(frozen=True)
class ConnectionMetadata:
    """
    Represents the complete metadata required to create a
    source or target database connection.

    This object is created by ConnectionService after reading
    the metadata database.

    ConnectorFactory then uses connector_code to determine
    which database adapter should be instantiated.
    """

    # ---------------------------------------------------------
    # Metadata connection identification
    # ---------------------------------------------------------

    connection_id: int
    connection_name: str

    # ---------------------------------------------------------
    # Connector information
    #
    # Example:
    #
    # connector_code = POSTGRESQL_CONNECTOR
    #
    # Later:
    #
    # MYSQL_CONNECTOR
    # SQLSERVER_CONNECTOR
    # ORACLE_CONNECTOR
    # SNOWFLAKE_CONNECTOR
    # ---------------------------------------------------------

    connector_id: int
    connector_code: str
    connector_name: str

    connector_version_id: int
    connector_version: str

    # ---------------------------------------------------------
    # Physical connection information
    # ---------------------------------------------------------

    host_name: str | None
    port_no: int | None
    database_name: str | None
    endpoint_url: str | None

    # ---------------------------------------------------------
    # Credential reference
    #
    # IMPORTANT:
    # We store the reference/ID here, not the actual password.
    # ---------------------------------------------------------

    credential_id: int | None

    # ---------------------------------------------------------
    # Connection role
    #
    # Examples:
    #
    # SOURCE
    # TARGET
    # CONTROL
    # ---------------------------------------------------------

    connection_role_code: str

    # ---------------------------------------------------------
    # Runtime settings
    # ---------------------------------------------------------

    connect_timeout_seconds: int
    command_timeout_seconds: int

    # ---------------------------------------------------------
    # Dynamic parameters
    #
    # Example:
    #
    # {
    #     "username": ConnectionParameter(...)
    # }
    #
    # Later database-specific parameters can be added without
    # changing this model.
    # ---------------------------------------------------------

    parameters: dict[str, ConnectionParameter]