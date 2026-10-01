"""
Metadata Store Connection Test
===============================

Purpose
-------

This script verifies that the application can connect to the
PostgreSQL metadata/control database.

It does NOT connect to the source database.

It does NOT insert, update, or delete any data.

Current architecture:

    Python Application
            |
            v
       config.py
            |
            v
       metastore.py
            |
            v
    PostgreSQL Metadata DB
            |
            v
        Connection
        Successful


Why do we need this test?
-------------------------

Before ConnectionService can read:

    conn.connection_profile
    conn.connection_parameter
    conn.connector
    conn.connector_version

we first need to prove that the application can successfully
connect to the metadata database.
"""


from app.db.metastore import (
    get_metastore_connection,
)


def main() -> None:
    """
    Test the metadata PostgreSQL database connection.
    """

    print()
    print("=" * 70)
    print("METADATA STORE CONNECTION TEST")
    print("=" * 70)

    try:

        # =====================================================
        # OPEN METADATA DATABASE CONNECTION
        # =====================================================
        #
        # get_metastore_connection() reads the connection
        # configuration from app/core/config.py.
        #
        # The actual values come from the environment/.env.
        # =====================================================

        with get_metastore_connection() as connection:

            print(
                "Metadata database connection successful!"
            )

            # -------------------------------------------------
            # Display safe connection information.
            #
            # We intentionally do NOT display the password.
            # -------------------------------------------------

            print(
                f"Database : "
                f"{connection.info.dbname}"
            )

            print(
                f"Host     : "
                f"{connection.info.host}"
            )

            print(
                f"Port     : "
                f"{connection.info.port}"
            )

            print(
                f"User     : "
                f"{connection.info.user}"
            )

            # -------------------------------------------------
            # Execute a simple read-only query.
            #
            # SELECT 1 confirms that the database connection
            # is usable, not merely that it was created.
            # -------------------------------------------------

            with connection.cursor() as cursor:

                cursor.execute(
                    "SELECT 1;"
                )

                result = cursor.fetchone()

                if result != (1,):

                    raise RuntimeError(
                        "Metadata database SELECT 1 "
                        "test failed."
                    )

            print(
                "Metadata database query test successful!"
            )

        # =====================================================
        # CONNECTION IS AUTOMATICALLY CLOSED HERE
        # =====================================================
        #
        # The context manager inside metastore.py handles the
        # connection cleanup.
        # =====================================================

        print(
            "Metadata database connection closed."
        )

        print("=" * 70)
        print(
            "METADATA STORE TEST PASSED"
        )
        print("=" * 70)

    except Exception as exc:

        # =====================================================
        # ERROR HANDLING
        # =====================================================
        #
        # We print the exception type and message, but we do
        # not print passwords or other secrets.
        # =====================================================

        print()
        print("=" * 70)
        print("METADATA STORE TEST FAILED")
        print("=" * 70)

        print(
            f"Error Type : "
            f"{type(exc).__name__}"
        )

        print(
            f"Error      : "
            f"{exc}"
        )

        print("=" * 70)

        # Return a non-zero exit code to indicate failure.
        raise


if __name__ == "__main__":
    main()