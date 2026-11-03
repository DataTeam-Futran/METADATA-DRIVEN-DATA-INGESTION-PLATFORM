"""
Metadata Store Database Connection
==================================

This module manages the connection between the application and
the PostgreSQL metadata/control database.

IMPORTANT
---------

This database is NOT the source database.

It is the control-plane database that stores metadata such as:

    conn.connection_profile
    conn.connection_parameter
    conn.connector
    conn.connector_version

The application first connects to this metadata database to
understand HOW and WHERE it should connect to a source database.

Architecture:

    Application
         |
         v
    Metadata Store
         |
         +-- connection_profile
         +-- connection_parameter
         +-- connector
         +-- connector_version
         |
         v
    ConnectionMetadata
         |
         v
    Source Connector
"""


from contextlib import contextmanager
from typing import Generator

import psycopg

from app.core.config import get_settings


@contextmanager
def get_metastore_connection(
) -> Generator[psycopg.Connection, None, None]:
    """
    Create and manage a connection to the metadata PostgreSQL
    database.

    WHY THIS FUNCTION EXISTS
    ------------------------
    The application has many services that need to read metadata.

    Instead of every service creating its own PostgreSQL connection,
    they all use this common function.

    Example:

        ConnectionService
              |
              v
        get_metastore_connection()
              |
              v
        PostgreSQL Metadata DB

    The context manager automatically closes the connection after
    the operation completes.

    Yields
    ------
    psycopg.Connection
        Active PostgreSQL metadata database connection.

    Raises
    ------
    psycopg.Error
        If the metadata database connection cannot be established.
    """

    # =========================================================
    # LOAD APPLICATION CONFIGURATION
    # =========================================================
    #
    # Configuration comes from environment variables.
    #
    # We do NOT hardcode:
    #
    #     host
    #     username
    #     password
    #     database
    #
    # inside the Python source code.
    # =========================================================

    settings = get_settings()

    connection = None

    try:

        # =====================================================
        # CREATE METADATA DATABASE CONNECTION
        # =====================================================

        connection = psycopg.connect(
            host=settings.metastore_host,
            port=settings.metastore_port,
            dbname=settings.metastore_database,
            user=settings.metastore_username,
            password=settings.metastore_password,
            sslmode=settings.metastore_sslmode,
            connect_timeout=(
                settings.metastore_connect_timeout
            ),
        )

        # -----------------------------------------------------
        # Return the active connection to the caller.
        # -----------------------------------------------------

        yield connection

    finally:

        # =====================================================
        # ALWAYS CLOSE THE CONNECTION
        # =====================================================
        #
        # This is important for a production application.
        #
        # If an exception occurs while querying metadata,
        # the database connection must still be released.
        # =====================================================

        if connection is not None:

            connection.close()