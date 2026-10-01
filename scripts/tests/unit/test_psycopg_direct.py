"""
Psycopg Connection Diagnostic
=============================

Purpose
-------

The PostgreSQL server is reachable and psql can connect successfully,
but psycopg is currently receiving:

    server closed the connection unexpectedly

This script isolates the psycopg connection layer.

We test:

    1. Default PostgreSQL connection
    2. SSL disabled
    3. SSL required

WHY?

PostgreSQL clients can negotiate SSL differently. Testing the modes
separately helps identify whether SSL negotiation is involved.

This script performs only read-only connection tests.
"""


import os

import psycopg

from dotenv import load_dotenv


# =============================================================
# LOAD ENVIRONMENT
# =============================================================

load_dotenv()


def get_required(name: str) -> str:
    """
    Read a required environment variable.

    The actual password is never printed.
    """

    value = os.getenv(name)

    if not value:

        raise RuntimeError(
            f"Missing environment variable: {name}"
        )

    return value


def test_connection(
    connection_name: str,
    **connection_options,
) -> bool:
    """
    Attempt one PostgreSQL connection.

    Returns True when successful.
    Returns False when unsuccessful.

    The exception is displayed so we can identify the
    exact psycopg failure.
    """

    print()
    print("-" * 70)
    print(
        f"TEST: {connection_name}"
    )
    print("-" * 70)

    try:

        with psycopg.connect(
            **connection_options
        ) as connection:

            print(
                "Connection successful!"
            )

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

            print(
                "TEST PASSED"
            )

            return True

    except Exception as exc:

        print(
            "TEST FAILED"
        )

        print(
            f"Error Type : {type(exc).__name__}"
        )

        print(
            f"Error      : {exc}"
        )

        return False


def main() -> None:

    print()
    print("=" * 70)
    print("PSYCGOPG CONNECTION DIAGNOSTIC")
    print("=" * 70)

    # =========================================================
    # READ CONNECTION INFORMATION
    # =========================================================

    host = get_required(
        "MDIP_METASTORE_HOST"
    )

    port = int(
        get_required(
            "MDIP_METASTORE_PORT"
        )
    )

    database = get_required(
        "MDIP_METASTORE_DATABASE"
    )

    username = get_required(
        "MDIP_METASTORE_USERNAME"
    )

    password = get_required(
        "MDIP_METASTORE_PASSWORD"
    )

    print(
        f"Host     : {host}"
    )

    print(
        f"Port     : {port}"
    )

    print(
        f"Database : {database}"
    )

    print(
        f"Username : {username}"
    )

    print(
        "Password : CONFIGURED"
    )

    # =========================================================
    # COMMON CONNECTION SETTINGS
    # =========================================================

    common = {
        "host": host,
        "port": port,
        "dbname": database,
        "user": username,
        "password": password,
        "connect_timeout": 10,
    }

    # =========================================================
    # TEST 1 — DEFAULT
    # =========================================================

    default_success = test_connection(
        "Default psycopg connection",
        **common,
    )

    # =========================================================
    # TEST 2 — SSL DISABLED
    # =========================================================

    ssl_disabled_success = test_connection(
        "SSL disabled",
        **common,
        sslmode="disable",
    )

    # =========================================================
    # TEST 3 — SSL REQUIRED
    # =========================================================

    ssl_required_success = test_connection(
        "SSL required",
        **common,
        sslmode="require",
    )

    # =========================================================
    # FINAL RESULT
    # =========================================================

    print()
    print("=" * 70)
    print("DIAGNOSTIC SUMMARY")
    print("=" * 70)

    print(
        f"Default       : "
        f"{'PASS' if default_success else 'FAIL'}"
    )

    print(
        f"SSL disabled  : "
        f"{'PASS' if ssl_disabled_success else 'FAIL'}"
    )

    print(
        f"SSL required  : "
        f"{'PASS' if ssl_required_success else 'FAIL'}"
    )

    print("=" * 70)


if __name__ == "__main__":
    main()