"""
Application Configuration
=========================

This module manages configuration for the Metadata-Driven Data
Ingestion Platform.

WHY THIS FILE EXISTS
--------------------
Database credentials, host names and environment-specific
settings should NOT be hardcoded inside application code.

Instead, the application reads them from environment variables.

For local development:

    .env

For higher environments such as UAT/PROD:

    Environment variables
    or
    Secret/configuration management platform


CURRENT ARCHITECTURE
--------------------

Metadata Database
    |
    +-- PostgreSQL
    |
    +-- conn
    +-- catalog
    +-- dtype
    +-- gov
    +-- ingest
    +-- map
    +-- orch
    +-- quality
    +-- runtime
    +-- sec
    +-- ui
    +-- etc.


IMPORTANT
---------

This configuration module is responsible ONLY for configuration.

It does NOT:

    - create database connections
    - execute SQL
    - read source metadata
    - run ingestion
    - create target tables

Those responsibilities belong to other application layers.
"""

import os

from dataclasses import dataclass

from dotenv import load_dotenv


# =============================================================
# LOAD ENVIRONMENT VARIABLES
# =============================================================
#
# During local development, configuration is loaded from:
#
#     .env
#
# Example:
#
#     MDIP_METASTORE_HOST=192.168.11.91
#     MDIP_METASTORE_PORT=5432
#     MDIP_METASTORE_DATABASE=Futran
#     MDIP_METASTORE_USERNAME=postgres
#     MDIP_METASTORE_PASSWORD=********
#     MDIP_METASTORE_CONNECT_TIMEOUT=10
#     MDIP_METASTORE_SSLMODE=disable
#
# IMPORTANT:
# ----------
# .env must NEVER be committed to Git.
#
# Production environments should provide these values through
# environment variables or an approved secrets management
# mechanism.
# =============================================================

load_dotenv()


# =============================================================
# SETTINGS DATA CLASS
# =============================================================

@dataclass(frozen=True)
class Settings:
    """
    Immutable application configuration.

    WHY frozen=True?
    ----------------
    Once configuration has been loaded, application components
    should not accidentally modify the configuration during
    runtime.

    This object represents the configuration required to connect
    to the metadata/control database.
    """

    # ---------------------------------------------------------
    # Metadata PostgreSQL server
    # ---------------------------------------------------------

    metastore_host: str

    metastore_port: int

    metastore_database: str

    metastore_username: str

    metastore_password: str

    # ---------------------------------------------------------
    # PostgreSQL connection timeout
    # ---------------------------------------------------------
    #
    # Maximum number of seconds the application waits while
    # establishing the metadata database connection.
    # ---------------------------------------------------------

    metastore_connect_timeout: int = 10

    # ---------------------------------------------------------
    # PostgreSQL SSL mode
    # ---------------------------------------------------------
    #
    # Examples:
    #
    #     disable
    #     allow
    #     prefer
    #     require
    #     verify-ca
    #     verify-full
    #
    # Your current PostgreSQL development server does not
    # support SSL, therefore your current .env should use:
    #
    #     MDIP_METASTORE_SSLMODE=disable
    #
    # In production, this value should be selected based on
    # the organization's PostgreSQL security configuration.
    # ---------------------------------------------------------

    metastore_sslmode: str = "disable"


# =============================================================
# REQUIRED ENVIRONMENT VARIABLE HELPER
# =============================================================

def _get_required_environment_variable(
    variable_name: str,
) -> str:
    """
    Read a required environment variable.

    Parameters
    ----------
    variable_name:
        Name of the environment variable.

    Returns
    -------
    str
        Cleaned environment variable value.

    Raises
    ------
    RuntimeError
        If the environment variable is missing or empty.

    WHY?
    ----
    The application should fail fast if a required configuration
    value is missing.

    For example, starting the application without a database
    host or username should produce a clear configuration error
    instead of a confusing database connection error later.
    """

    value = os.getenv(variable_name)

    if value is None or not value.strip():

        raise RuntimeError(
            f"Required environment variable "
            f"'{variable_name}' is not configured."
        )

    return value.strip()


# =============================================================
# GET SETTINGS
# =============================================================

def get_settings() -> Settings:
    """
    Build and return validated application settings.

    Returns
    -------
    Settings
        Immutable and validated application configuration.

    REQUIRED ENVIRONMENT VARIABLES
    --------------------------------

        MDIP_METASTORE_HOST
        MDIP_METASTORE_PORT
        MDIP_METASTORE_DATABASE
        MDIP_METASTORE_USERNAME
        MDIP_METASTORE_PASSWORD

    OPTIONAL ENVIRONMENT VARIABLES
    --------------------------------

        MDIP_METASTORE_CONNECT_TIMEOUT
        MDIP_METASTORE_SSLMODE

    WHY?
    ----
    All application components should obtain configuration
    through this function.

    This prevents individual modules from reading .env directly
    and makes configuration centralized and consistent.
    """

    # =========================================================
    # READ REQUIRED SETTINGS
    # =========================================================

    host = _get_required_environment_variable(
        "MDIP_METASTORE_HOST"
    )

    port_value = _get_required_environment_variable(
        "MDIP_METASTORE_PORT"
    )

    database = _get_required_environment_variable(
        "MDIP_METASTORE_DATABASE"
    )

    username = _get_required_environment_variable(
        "MDIP_METASTORE_USERNAME"
    )

    password = _get_required_environment_variable(
        "MDIP_METASTORE_PASSWORD"
    )

    # =========================================================
    # VALIDATE PORT
    # =========================================================
    #
    # PostgreSQL uses TCP port 5432 by default, but we don't
    # hardcode 5432 here because different environments may
    # use different ports.
    # =========================================================

    try:

        port = int(port_value)

    except ValueError as exc:

        raise RuntimeError(
            "MDIP_METASTORE_PORT must be a valid integer."
        ) from exc

    if not 1 <= port <= 65535:

        raise RuntimeError(
            "MDIP_METASTORE_PORT must be between "
            "1 and 65535."
        )

    # =========================================================
    # READ CONNECTION TIMEOUT
    # =========================================================
    #
    # Default:
    #
    #     10 seconds
    #
    # The timeout prevents the application from waiting
    # indefinitely when the metadata database is unavailable.
    # =========================================================

    timeout_value = os.getenv(
        "MDIP_METASTORE_CONNECT_TIMEOUT",
        "10",
    )

    try:

        connect_timeout = int(
            timeout_value
        )

    except ValueError as exc:

        raise RuntimeError(
            "MDIP_METASTORE_CONNECT_TIMEOUT "
            "must be a valid integer."
        ) from exc

    if connect_timeout <= 0:

        raise RuntimeError(
            "MDIP_METASTORE_CONNECT_TIMEOUT "
            "must be greater than zero."
        )

    # =========================================================
    # READ SSL MODE
    # =========================================================
    #
    # PostgreSQL/libpq supports the following SSL modes:
    #
    #     disable
    #     allow
    #     prefer
    #     require
    #     verify-ca
    #     verify-full
    #
    # Your current Futran PostgreSQL server reported:
    #
    #     server does not support SSL
    #
    # Therefore:
    #
    #     MDIP_METASTORE_SSLMODE=disable
    #
    # is currently required for this development environment.
    #
    # IMPORTANT:
    # ----------
    # We keep this configurable because production may require
    # encrypted PostgreSQL connections.
    # =========================================================

    sslmode = os.getenv(
        "MDIP_METASTORE_SSLMODE",
        "disable",
    ).strip().lower()

    allowed_ssl_modes = {
        "disable",
        "allow",
        "prefer",
        "require",
        "verify-ca",
        "verify-full",
    }

    if sslmode not in allowed_ssl_modes:

        raise RuntimeError(
            "MDIP_METASTORE_SSLMODE must be one of: "
            + ", ".join(
                sorted(allowed_ssl_modes)
            )
        )

    # =========================================================
    # CREATE IMMUTABLE SETTINGS OBJECT
    # =========================================================
    #
    # At this point all configuration values have been:
    #
    #     1. Loaded
    #     2. Validated
    #     3. Normalized
    #
    # The resulting Settings object is then passed to the
    # database/application layers.
    # =========================================================

    return Settings(
        metastore_host=host,
        metastore_port=port,
        metastore_database=database,
        metastore_username=username,
        metastore_password=password,
        metastore_connect_timeout=connect_timeout,
        metastore_sslmode=sslmode,
    )