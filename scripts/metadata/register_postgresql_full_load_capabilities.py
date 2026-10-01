"""
Register PostgreSQL Full Load Capabilities

Purpose
-------
Register the capabilities required by the current Full Load POC for:

    PostgreSQL Connector Version 3

Required capabilities:

    SCHEMA_DISCOVERY
    FULL_LOAD_SOURCE
    FULL_LOAD_TARGET

Metadata relationship:

    conn.connector_version
            |
            | connector_version_id
            v
    conn.connector_version_capability
            |
            | capability_id
            v
    conn.connector_capability

Design principles
-----------------
This operation is:

- Transactional
- Idempotent
- Metadata-driven
- Safe against duplicate assignments
- Explicit about rollback on failure

IMPORTANT
---------
This script performs a REAL metadata write.

It modifies only:

    conn.connector_version_capability

It does not modify:
- source data
- target data
- catalog metadata
- mappings
- load configuration
"""


# ============================================================================
# IMPORTS
# ============================================================================

# PostgreSQL driver.
import psycopg

# Centralized metadata-store connection manager.
from app.db.metastore import get_metastore_connection


# ============================================================================
# CONSTANTS
# ============================================================================

# PostgreSQL connector version used by the current POC.
POSTGRESQL_CONNECTOR_VERSION_ID = 3

# Capabilities required for the current Full Load implementation.
REQUIRED_CAPABILITY_CODES = (
    "SCHEMA_DISCOVERY",
    "FULL_LOAD_SOURCE",
    "FULL_LOAD_TARGET",
)


# ============================================================================
# OUTPUT HELPER
# ============================================================================

def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    This makes the execution output easier to review.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


# ============================================================================
# RESOLVE CAPABILITY IDS
# ============================================================================

def resolve_capability_ids(
    cursor: psycopg.Cursor,
) -> dict[str, int]:
    """
    Resolve capability IDs from stable capability codes.

    Why:
    ----
    Capability IDs are database-generated metadata identifiers.

    The application should not assume:

        SCHEMA_DISCOVERY = 1
        FULL_LOAD_SOURCE = 2
        FULL_LOAD_TARGET = 3

    Instead, the stable capability_code is used to resolve the current ID.
    """

    # Retrieve capability definitions using their stable codes.
    query = """
        SELECT
            capability_id,
            capability_code
        FROM conn.connector_capability
        WHERE capability_code = ANY(%s)
        ORDER BY capability_id;
    """

    # Execute the parameterized query.
    cursor.execute(
        query,
        (list(REQUIRED_CAPABILITY_CODES),),
    )

    # Fetch all matching capabilities.
    records = cursor.fetchall()

    # Convert the result into a code -> ID dictionary.
    capability_ids = {
        capability_code: capability_id
        for capability_id, capability_code in records
    }

    # Validate that every required capability exists.
    missing_capabilities = [
        capability_code
        for capability_code in REQUIRED_CAPABILITY_CODES
        if capability_code not in capability_ids
    ]

    # Stop before modifying anything if metadata is incomplete.
    if missing_capabilities:
        raise RuntimeError(
            "Required capability definitions are missing: "
            + ", ".join(missing_capabilities)
        )

    return capability_ids


# ============================================================================
# VALIDATE CONNECTOR VERSION
# ============================================================================

def validate_connector_version(
    cursor: psycopg.Cursor,
) -> None:
    """
    Validate that connector version 3 exists and is active.

    This prevents accidentally assigning capabilities to an invalid or
    inactive connector version.
    """

    # Retrieve connector version information.
    query = """
        SELECT
            connector_version_id,
            connector_id,
            semantic_version,
            status_code
        FROM conn.connector_version
        WHERE connector_version_id = %s;
    """

    # Execute the query.
    cursor.execute(
        query,
        (POSTGRESQL_CONNECTOR_VERSION_ID,),
    )

    # Fetch the connector version.
    record = cursor.fetchone()

    # Fail if the connector version does not exist.
    if record is None:
        raise RuntimeError(
            f"Connector version {POSTGRESQL_CONNECTOR_VERSION_ID} "
            "does not exist."
        )

    # Extract the important metadata values.
    (
        connector_version_id,
        connector_id,
        semantic_version,
        status_code,
    ) = record

    # Display the validated connector version.
    print(
        f"Connector Version : {connector_version_id}"
    )
    print(
        f"Connector ID      : {connector_id}"
    )
    print(
        f"Semantic Version  : {semantic_version}"
    )
    print(
        f"Status            : {status_code}"
    )

    # Only active connector versions should receive runtime capabilities.
    if status_code != "ACTIVE":
        raise RuntimeError(
            f"Connector version {connector_version_id} is not ACTIVE."
        )


# ============================================================================
# INSERT CAPABILITY ASSIGNMENTS
# ============================================================================

def register_capabilities(
    cursor: psycopg.Cursor,
    capability_ids: dict[str, int],
) -> list[str]:
    """
    Register the required capabilities.

    The operation uses ON CONFLICT DO NOTHING because the table has:

        PRIMARY KEY (connector_version_id, capability_id)

    This makes the operation idempotent.

    If the assignment already exists, it is left unchanged.
    """

    # Store the capabilities that are actually inserted.
    inserted_capabilities: list[str] = []

    # Insert each required capability independently within the same
    # transaction.
    for capability_code in REQUIRED_CAPABILITY_CODES:

        # Resolve the capability ID dynamically.
        capability_id = capability_ids[capability_code]

        # Insert the connector-version capability assignment.
        #
        # is_supported = TRUE means this connector version explicitly
        # supports the capability.
        #
        # capability_value is left NULL because these three capabilities
        # are BOOLEAN capabilities and currently do not require additional
        # configuration.
        #
        # created_at, updated_at, and row_version use database defaults.
        query = """
            INSERT INTO conn.connector_version_capability (
                connector_version_id,
                capability_id,
                is_supported,
                capability_value
            )
            VALUES (
                %s,
                %s,
                TRUE,
                NULL
            )
            ON CONFLICT (
                connector_version_id,
                capability_id
            )
            DO NOTHING
            RETURNING capability_id;
        """

        # Execute the insert.
        cursor.execute(
            query,
            (
                POSTGRESQL_CONNECTOR_VERSION_ID,
                capability_id,
            ),
        )

        # RETURNING returns a row only when a new record was inserted.
        inserted_record = cursor.fetchone()

        if inserted_record is not None:
            inserted_capabilities.append(
                capability_code
            )

    return inserted_capabilities


# ============================================================================
# VERIFY CAPABILITY ASSIGNMENTS
# ============================================================================

def verify_capabilities(
    cursor: psycopg.Cursor,
) -> None:
    """
    Verify the final capability assignments inside the current transaction.

    This is performed before commit so that a verification failure can also
    cause the transaction to roll back.
    """

    # Retrieve the required capability assignments.
    query = """
        SELECT
            connector_version_capability.connector_version_id,
            connector_capability.capability_code,
            connector_version_capability.is_supported,
            connector_version_capability.capability_value
        FROM conn.connector_version_capability
        INNER JOIN conn.connector_capability
            ON connector_capability.capability_id =
               connector_version_capability.capability_id
        WHERE connector_version_capability.connector_version_id = %s
          AND connector_capability.capability_code = ANY(%s)
        ORDER BY connector_capability.capability_code;
    """

    # Execute the verification query.
    cursor.execute(
        query,
        (
            POSTGRESQL_CONNECTOR_VERSION_ID,
            list(REQUIRED_CAPABILITY_CODES),
        ),
    )

    # Fetch the assignments.
    records = cursor.fetchall()

    # Convert returned capability codes into a set.
    supported_capabilities = {
        capability_code
        for (
            connector_version_id,
            capability_code,
            is_supported,
            capability_value,
        ) in records
        if is_supported is True
    }

    # Determine whether any required capability is missing.
    missing_capabilities = [
        capability_code
        for capability_code in REQUIRED_CAPABILITY_CODES
        if capability_code not in supported_capabilities
    ]

    # Fail the transaction if verification is incomplete.
    if missing_capabilities:
        raise RuntimeError(
            "Capability verification failed. Missing supported "
            "capabilities: "
            + ", ".join(missing_capabilities)
        )

    # Display the verified assignments.
    print()
    print("Verified capabilities:")

    for (
        connector_version_id,
        capability_code,
        is_supported,
        capability_value,
    ) in records:

        print(
            f"{capability_code:<25} | "
            f"supported={is_supported} | "
            f"value={capability_value}"
        )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """
    Register and verify PostgreSQL Full Load capabilities.

    Transaction behavior
    --------------------
    Success:
        INSERT -> VERIFY -> COMMIT

    Failure:
        INSERT/VERIFY -> ROLLBACK
    """

    # Display operation title.
    print_section(
        "REGISTER POSTGRESQL FULL LOAD CAPABILITIES"
    )

    # Open the metadata-store connection.
    #
    # The connection manager itself does not auto-commit.
    # Therefore this function explicitly controls the transaction.
    with get_metastore_connection() as connection:

        try:
            # Open a cursor for the complete transaction.
            with connection.cursor() as cursor:

                # ----------------------------------------------------------
                # Step 1: Validate connector version.
                # ----------------------------------------------------------

                print("Validating connector version...")
                validate_connector_version(cursor)

                # ----------------------------------------------------------
                # Step 2: Resolve capability IDs dynamically.
                # ----------------------------------------------------------

                print()
                print("Resolving capability definitions...")

                capability_ids = resolve_capability_ids(cursor)

                # Display the resolved IDs.
                for capability_code in REQUIRED_CAPABILITY_CODES:
                    print(
                        f"{capability_code:<25} : "
                        f"{capability_ids[capability_code]}"
                    )

                # ----------------------------------------------------------
                # Step 3: Register capabilities.
                # ----------------------------------------------------------

                print()
                print("Registering capability assignments...")

                inserted_capabilities = register_capabilities(
                    cursor,
                    capability_ids,
                )

                # Display newly inserted assignments.
                if inserted_capabilities:
                    print("New assignments:")

                    for capability_code in inserted_capabilities:
                        print(
                            f"  + {capability_code}"
                        )

                else:
                    # This means the operation was already completed earlier.
                    print(
                        "No new assignments were required. "
                        "Existing assignments were preserved."
                    )

                # ----------------------------------------------------------
                # Step 4: Verify before commit.
                # ----------------------------------------------------------

                print()
                print("Verifying capability assignments...")

                verify_capabilities(cursor)

            # --------------------------------------------------------------
            # Step 5: Commit only after successful verification.
            # --------------------------------------------------------------

            connection.commit()

            print()
            print("TRANSACTION COMMITTED SUCCESSFULLY")

        except Exception:
            # Roll back every metadata change made during this operation.
            connection.rollback()

            # Display the rollback status.
            print()
            print("TRANSACTION ROLLED BACK")

            # Re-raise the original exception so the command exits with
            # a failure status and the actual error remains visible.
            raise

    # Final status message.
    print()
    print("=" * 100)
    print("CAPABILITY REGISTRATION COMPLETE")
    print("=" * 100)


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

# Execute main() only when this file is run directly.
if __name__ == "__main__":
    main()