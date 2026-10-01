# ============================================================
# DATABASE CONNECTION MODULE
# ============================================================
#
# PURPOSE:
# This module is responsible only for creating a connection
# to the Futran metadata database.
#
# It should NOT contain business logic or metadata queries.
#
# Other application components can reuse this database
# connection instead of creating their own connection code.
#
# ============================================================

import getpass
import psycopg


# ============================================================
# DATABASE CONFIGURATION
# ============================================================
#
# These details identify the PostgreSQL database that stores
# our metadata.
#
# IMPORTANT:
# This is the FUTRAN metadata database.
# It is NOT the demo source database.
#
# ============================================================

DB_HOST = "192.168.11.91"
DB_PORT = 5432
DB_NAME = "Futran"
DB_USER = "postgres"


# ============================================================
# CREATE DATABASE CONNECTION
# ============================================================
#
# WHY:
# The application needs a reusable function that can establish
# a connection whenever a service needs to access metadata.
#
# ============================================================

def get_db_connection():
    """
    Create and return a PostgreSQL connection to the
    Futran metadata database.
    """

    # --------------------------------------------------------
    # Ask for the password without displaying it on screen.
    # --------------------------------------------------------

    db_password = getpass.getpass(
        "Enter PostgreSQL password: "
    )

    # --------------------------------------------------------
    # Create the PostgreSQL connection using psycopg.
    # --------------------------------------------------------

    connection = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=db_password
    )

    return connection