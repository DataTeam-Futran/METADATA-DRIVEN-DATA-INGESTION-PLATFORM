# ============================================================
# SOURCE DATABASE CONNECTION MODULE
# ============================================================
#
# PURPOSE:
# This module is responsible for connecting to the SOURCE
# database using connection metadata retrieved from Futran.
#
# IMPORTANT:
# This module does NOT contain metadata queries.
#
# The metadata is retrieved by:
#
#     app/services/connection_service.py
#
# This module only uses that metadata to establish a
# connection to the source database.
#
# ============================================================

import getpass
import psycopg


# ============================================================
# CONNECT TO SOURCE DATABASE
# ============================================================
#
# WHY:
# The ingestion platform must be able to connect to a source
# database dynamically.
#
# We should NOT hard-code:
#
#     demo_source_db
#     localhost
#     5432
#
# Instead, these values will come from the metadata database.
#
# ============================================================

def get_source_db_connection(connection_metadata):
    """
    Create a connection to the source database using
    metadata retrieved from Futran.
    """

    # --------------------------------------------------------
    # Extract source database details from metadata.
    #
    # These values came from conn.connection_profile.
    # --------------------------------------------------------

    host = connection_metadata["host_name"]
    port = connection_metadata["port_no"]
    database = connection_metadata["database_name"]

    # --------------------------------------------------------
    # Ask for the source database password securely.
    #
    # We do not store the actual password in source code.
    #
    # IMPORTANT:
    # secret_ref is a reference to a secret.
    # It is NOT the actual database password.
    # --------------------------------------------------------

    password = getpass.getpass(
        "Enter source PostgreSQL password: "
    )

    # --------------------------------------------------------
    # Create the source database connection.
    #
    # These values are coming from metadata instead of being
    # hard-coded in the application.
    # --------------------------------------------------------

    connection = psycopg.connect(
        host=host,
        port=port,
        dbname=database,
        user="postgres",
        password=password
    )

    return connection