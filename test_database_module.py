# ============================================================
# TEST DATABASE MODULE
# ============================================================
#
# WHY:
# We have moved the PostgreSQL connection logic into
# app.db.database.
#
# This test verifies that the new module can successfully
# create a connection to the Futran database.
#
# ============================================================

from app_prod.db.database import get_db_connection


try:

    # --------------------------------------------------------
    # Request a connection from our reusable database module.
    # --------------------------------------------------------

    connection = get_db_connection()

    print("Database connection successful!")

    # --------------------------------------------------------
    # Verify which database we connected to.
    # --------------------------------------------------------

    with connection.cursor() as cursor:

        cursor.execute(
            "SELECT current_database(), current_user;"
        )

        database_name, current_user = cursor.fetchone()

        print("Database:", database_name)
        print("User:", current_user)

    # --------------------------------------------------------
    # Close the connection after testing.
    # --------------------------------------------------------

    connection.close()

    print("Database connection closed.")

except Exception as error:

    print("Database connection failed.")
    print("Error:", error)