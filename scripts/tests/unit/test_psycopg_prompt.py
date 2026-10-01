"""
Interactive Psycopg PostgreSQL Connection Test
===============================================

Purpose
-------

This script tests the PostgreSQL connection using psycopg.

Unlike test_psycopg_direct.py, this script does NOT read the
password from .env.

Instead, it asks for the password interactively.

This helps us determine whether the problem is:

    A. The PostgreSQL password itself
    B. The password stored in .env
    C. The Python/psycopg connection

The password is entered using getpass, so it is not displayed.
"""

import getpass

import psycopg


def main() -> None:
    """
    Test PostgreSQL connectivity using a manually entered password.
    """

    # =========================================================
    # CONNECTION DETAILS
    # =========================================================
    #
    # These values have already been confirmed through your
    # successful psql connection.
    # =========================================================

    host = "192.168.11.91"
    port = 5432
    database = "Futran"
    username = "postgres"

    print()
    print("=" * 70)
    print("INTERACTIVE PSYCGOPG CONNECTION TEST")
    print("=" * 70)

    print(f"Host     : {host}")
    print(f"Port     : {port}")
    print(f"Database : {database}")
    print(f"Username : {username}")

    # =========================================================
    # GET PASSWORD SECURELY
    # =========================================================
    #
    # getpass does not display the password while typing.
    #
    # This is only a diagnostic test. Later, the production
    # application will retrieve credentials through the
    # configured credential mechanism.
    # =========================================================

    password = getpass.getpass(
        "Enter PostgreSQL password: "
    )

    print()
    print("Connecting to PostgreSQL...")

    try:

        # =====================================================
        # CONNECT TO POSTGRESQL
        # =====================================================
        #
        # sslmode="disable" is intentional for this test because
        # your PostgreSQL server reported:
        #
        #     server does not support SSL
        #
        # We will handle production security separately.
        # =====================================================

        with psycopg.connect(
            host=host,
            port=port,
            dbname=database,
            user=username,
            password=password,
            sslmode="disable",
            connect_timeout=10,
        ) as connection:

            print(
                "PostgreSQL connection successful!"
            )

            # =================================================
            # VERIFY THE ACTIVE DATABASE CONNECTION
            # =================================================

            with connection.cursor() as cursor:

                cursor.execute(
                    """
                    SELECT
                        current_database(),
                        current_user,
                        inet_server_addr(),
                        inet_server_port();
                    """
                )

                row = cursor.fetchone()

                print()
                print(
                    f"Database       : {row[0]}"
                )

                print(
                    f"User           : {row[1]}"
                )

                print(
                    f"Server Address : {row[2]}"
                )

                print(
                    f"Server Port    : {row[3]}"
                )

                # =================================================
                # VERIFY THE METADATA SCHEMA
                # =================================================
                #
                # Your metadata database contains the conn schema.
                #
                # We verify that it is visible from this connection.
                # =================================================

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'conn';
                    """
                )

                table_count = cursor.fetchone()[0]

                print()
                print(
                    f"Tables in conn schema : {table_count}"
                )

            print()
            print("=" * 70)
            print("INTERACTIVE PSYCGOPG TEST PASSED")
            print("=" * 70)

    except Exception as exc:

        print()
        print("=" * 70)
        print("INTERACTIVE PSYCGOPG TEST FAILED")
        print("=" * 70)

        print(
            f"Error Type : {type(exc).__name__}"
        )

        print(
            f"Error      : {exc}"
        )

        print("=" * 70)

        raise


if __name__ == "__main__":
    main()