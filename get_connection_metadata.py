# ============================================================
# STEP 13C: RETRIEVE CONNECTION METADATA
# ============================================================
#
# WHY:
# We have already confirmed that Python can connect to the
# Futran metadata database.
#
# Now we want Python to retrieve the connection information
# that we created earlier in the conn schema.
#
# This is the first actual metadata-driven operation.
#
# ============================================================

import getpass
import psycopg


# ------------------------------------------------------------
# DATABASE CONNECTION DETAILS
# ------------------------------------------------------------
#
# These details are for connecting to the METADATA database.
# They are NOT the source database connection details.
#
# ------------------------------------------------------------

DB_HOST = "192.168.11.91"
DB_PORT = 5432
DB_NAME = "Futran"
DB_USER = "postgres"


# ------------------------------------------------------------
# GET DATABASE PASSWORD
# ------------------------------------------------------------
#
# We do not hard-code the password inside Python source code.
#
# ------------------------------------------------------------

DB_PASSWORD = getpass.getpass("Enter PostgreSQL password: ")


# ------------------------------------------------------------
# SQL QUERY
# ------------------------------------------------------------
#
# connection_profile contains:
#
#   host_name
#   port_no
#   database_name
#   endpoint_url
#
# credential_ref contains:
#
#   secret_ref
#   credential_name
#
# We join the two tables using credential_id.
#
# ------------------------------------------------------------

QUERY = """
SELECT
    cp.database_name,
    cp.endpoint_url,
    cp.host_name,
    cp.port_no,
    cr.secret_ref,
    cr.credential_name
FROM conn.connection_profile AS cp
INNER JOIN conn.credential_ref AS cr
    ON cp.credential_id = cr.credential_id
WHERE cp.connection_id = %s;
"""


# ------------------------------------------------------------
# CONNECT TO FUTRAN
# ------------------------------------------------------------

try:

    connection = psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

    print("Connected to Futran metadata database.")


    # --------------------------------------------------------
    # EXECUTE METADATA QUERY
    # --------------------------------------------------------
    #
    # connection_id is passed separately using %s.
    #
    # This is safer than directly building SQL strings.
    # --------------------------------------------------------

    with connection.cursor() as cursor:

        connection_id = 1

        cursor.execute(
            QUERY,
            (connection_id,)
        )

        result = cursor.fetchone()


    # --------------------------------------------------------
    # DISPLAY RESULT
    # --------------------------------------------------------

    if result:

        database_name = result[0]
        endpoint_url = result[1]
        host_name = result[2]
        port_no = result[3]
        secret_ref = result[4]
        credential_name = result[5]

        print("\nConnection Metadata")
        print("---------------------------")
        print("Database Name :", database_name)
        print("Endpoint URL  :", endpoint_url)
        print("Host Name     :", host_name)
        print("Port Number   :", port_no)
        print("Secret Ref    :", secret_ref)
        print("Credential    :", credential_name)

    else:

        print("No connection metadata found.")


    # --------------------------------------------------------
    # CLOSE DATABASE CONNECTION
    # --------------------------------------------------------

    connection.close()

    print("\nMetadata database connection closed.")


except Exception as error:

    print("Error while retrieving connection metadata.")
    print("Error:", error)