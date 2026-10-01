# ============================================================
# STEP 13B: TEST PYTHON → POSTGRESQL CONNECTION
# ============================================================
#
# WHY:
# We have already verified that PostgreSQL is working through
# pgAdmin.
#
# Now we need to verify that our Python application can also
# connect to the Futran metadata database.
#
# WHAT:
# - Uses psycopg 3
# - Connects to the Futran database
# - Uses the postgres database user
# - Does NOT store the password in the source code
#
# ============================================================

import getpass
import psycopg


# ------------------------------------------------------------
# DATABASE CONNECTION DETAILS
# ------------------------------------------------------------
# These are the local PostgreSQL details we have been using.
# ------------------------------------------------------------

DB_HOST = "192.168.11.91"
DB_PORT = 5432
DB_NAME = "Futran"
DB_USER = "postgres"


# ------------------------------------------------------------
# GET PASSWORD SECURELY
# ------------------------------------------------------------
# getpass prevents the password from being displayed while
# typing it in the terminal.
# ------------------------------------------------------------

DB_PASSWORD = getpass.getpass("Enter PostgreSQL password: ")


# ------------------------------------------------------------
# CREATE DATABASE CONNECTION
# ------------------------------------------------------------
# psycopg.connect() establishes the connection between our
# Python application and PostgreSQL.
# ------------------------------------------------------------

try:

    connection = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

    print("Database connection successful!")

    # --------------------------------------------------------
    # VERIFY THE CONNECTION
    # --------------------------------------------------------
    # A simple SELECT confirms that PostgreSQL is responding.
    # --------------------------------------------------------

    with connection.cursor() as cursor:

        cursor.execute("SELECT current_database(), current_user;")

        database_name, current_user = cursor.fetchone()

        print("Database:", database_name)
        print("User:", current_user)

    # --------------------------------------------------------
    # CLOSE CONNECTION
    # --------------------------------------------------------
    # We close the connection after the test.
    # --------------------------------------------------------

    connection.close()

    print("Database connection closed.")

except Exception as error:

    print("Database connection failed.")
    print("Error:", error)