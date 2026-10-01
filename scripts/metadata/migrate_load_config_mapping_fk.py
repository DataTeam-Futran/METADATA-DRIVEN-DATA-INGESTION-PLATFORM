"""
Migrate ingest.load_config to the new map.mapping_version model.

Purpose
-------
The current ingest.load_config table still has a foreign key to:

    ingest.mapping_version

The new metadata-driven architecture uses:

    map.mapping_version

Customer mapping version 2 exists only in map.mapping_version.

Therefore, Customer execution configuration cannot currently be
inserted into ingest.load_config.

This migration changes ONLY the foreign key of ingest.load_config.

It does NOT modify:

    ingest.mapping_version
    ingest.mapping_field
    ingest.mapping_source
    map.mapping_version
    map.mapping_field
    map.mapping_source

The legacy mapping tables remain untouched.

Safety
------
The migration performs a preflight validation before changing the FK.

Every existing ingest.load_config.mapping_version_id must already exist
in map.mapping_version.

If any value is missing, the migration aborts before ALTER TABLE.

The entire migration runs inside one database transaction.
"""


from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# Existing legacy foreign-key constraint.
#
# This is the constraint currently pointing to ingest.mapping_version.
# ---------------------------------------------------------------------------
OLD_CONSTRAINT_NAME = "fk_load_mapping_version"


# ---------------------------------------------------------------------------
# New foreign-key constraint name.
#
# A new descriptive name makes it clear that load_config now references
# the new map.mapping_version table.
# ---------------------------------------------------------------------------
NEW_CONSTRAINT_NAME = "fk_load_config_mapping_version"


def print_section(title: str) -> None:
    """
    Print a consistent section heading.

    Why:
    Makes migration output easier to review during development.
    """

    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def validate_existing_load_config_rows(connection) -> None:
    """
    Validate all existing load_config mapping version IDs.

    Why:
    We must not drop the existing FK unless every existing row can
    satisfy the new FK.

    If a legacy load_config row points to a mapping version that does
    not exist in map.mapping_version, this function raises an error.
    """

    query = """
        SELECT
            lc.load_config_id,
            lc.mapping_version_id
        FROM ingest.load_config lc
        LEFT JOIN map.mapping_version mv
            ON mv.mapping_version_id = lc.mapping_version_id
        WHERE mv.mapping_version_id IS NULL
        ORDER BY lc.load_config_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        invalid_rows = cursor.fetchall()

    # Abort the migration if any existing row would violate the new FK.
    if invalid_rows:
        raise RuntimeError(
            "Preflight validation failed. "
            "The following load_config rows do not have a matching "
            "map.mapping_version record: "
            f"{invalid_rows}"
        )

    print("Preflight validation: PASSED")
    print(
        "All existing ingest.load_config.mapping_version_id values "
        "exist in map.mapping_version."
    )


def verify_customer_mapping_version(connection) -> None:
    """
    Confirm that Customer mapping version 2 exists.

    Why:
    This is the mapping version that previously failed during
    execution configuration creation.
    """

    query = """
        SELECT
            mapping_version_id,
            tenant_id,
            mapping_id,
            version_no,
            status_code
        FROM map.mapping_version
        WHERE mapping_version_id = 2;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            "Customer mapping version 2 was not found in "
            "map.mapping_version."
        )

    print("Customer mapping version verification: PASSED")
    print(
        f"Mapping Version ID : {row[0]}"
    )
    print(
        f"Tenant ID           : {row[1]}"
    )
    print(
        f"Mapping ID          : {row[2]}"
    )
    print(
        f"Version Number      : {row[3]}"
    )
    print(
        f"Status              : {row[4]}"
    )


def verify_old_constraint(connection) -> None:
    """
    Confirm that the expected legacy FK currently exists.

    Why:
    We should never blindly drop a constraint.

    If the database has already been changed manually, the migration
    should stop instead of making assumptions.
    """

    query = """
        SELECT
            constraint_name
        FROM information_schema.table_constraints
        WHERE table_schema = 'ingest'
          AND table_name = 'load_config'
          AND constraint_type = 'FOREIGN KEY'
          AND constraint_name = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (OLD_CONSTRAINT_NAME,),
        )

        row = cursor.fetchone()

    if row is None:
        raise RuntimeError(
            f"Expected constraint '{OLD_CONSTRAINT_NAME}' "
            "was not found on ingest.load_config."
        )

    print(
        f"Existing constraint verification: PASSED "
        f"({OLD_CONSTRAINT_NAME})"
    )


def migrate_constraint(connection) -> None:
    """
    Replace the old FK with a new FK pointing to map.mapping_version.

    Why:
    This is the actual schema change required to allow the new
    metadata-driven mapping version to be used by load_config.

    Both statements execute inside the same transaction.
    """

    with connection.cursor() as cursor:

        # --------------------------------------------------------------
        # Remove the old FK pointing to the legacy mapping_version table.
        # --------------------------------------------------------------
        cursor.execute(
            f"""
            ALTER TABLE ingest.load_config
            DROP CONSTRAINT {OLD_CONSTRAINT_NAME};
            """
        )

        print(
            f"Dropped old constraint: {OLD_CONSTRAINT_NAME}"
        )

        # --------------------------------------------------------------
        # Add the new FK pointing to the authoritative new model.
        # --------------------------------------------------------------
        cursor.execute(
            f"""
            ALTER TABLE ingest.load_config
            ADD CONSTRAINT {NEW_CONSTRAINT_NAME}
            FOREIGN KEY (mapping_version_id)
            REFERENCES map.mapping_version(mapping_version_id);
            """
        )

        print(
            f"Created new constraint: {NEW_CONSTRAINT_NAME}"
        )


def verify_new_constraint(connection) -> None:
    """
    Verify that the new FK points to map.mapping_version.

    Why:
     PostgreSQL stores foreign-key definitions in pg_constraint.
    Reading pg_constraint directly gives us the authoritative
    constraint definition and avoids relying on an information_schema
    join that previously failed to locate the newly created FK.
    """

    query = """
        SELECT
            conname,
            pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conname = %s
          AND conrelid = 'ingest.load_config'::regclass;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (NEW_CONSTRAINT_NAME,),
        )

        row = cursor.fetchone()
 # Stop the migration if PostgreSQL did not register the new FK.
    if row is None:
        raise RuntimeError(
            "New load_config foreign key was not found after migration."
        )

    constraint_name = row[0]
    constraint_definition = row[1]

    # Verify that the constraint points to the new authoritative
    # mapping-version table, not the legacy table.
    expected_reference = (
        "REFERENCES map.mapping_version(mapping_version_id)"
    )

    if expected_reference not in constraint_definition:
        raise RuntimeError(
            "New load_config foreign key exists, but it does not "
            "reference map.mapping_version(mapping_version_id). "
            f"Actual definition: {constraint_definition}"
        )

    print()
    print("New constraint verification: PASSED")
    print(f"Constraint          : {constraint_name}")
    print(f"Definition          : {constraint_definition}")

def main() -> None:
    """
    Execute the load_config FK migration.

    Transaction behavior:
        - If every validation and ALTER succeeds → COMMIT.
        - If anything fails → ROLLBACK.
    """

    print("=" * 100)
    print("LOAD CONFIG FOREIGN KEY MIGRATION")
    print("=" * 100)

    with get_metastore_connection() as connection:

        try:
            # ----------------------------------------------------------
            # Phase 1: Validate existing load_config data.
            # ----------------------------------------------------------
            print_section("PHASE 1: PRE-FLIGHT VALIDATION")

            validate_existing_load_config_rows(
                connection
            )

            # ----------------------------------------------------------
            # Phase 2: Verify Customer mapping version.
            # ----------------------------------------------------------
            verify_customer_mapping_version(
                connection
            )

            # ----------------------------------------------------------
            # Phase 3: Verify expected current FK.
            # ----------------------------------------------------------
            verify_old_constraint(
                connection
            )

            # ----------------------------------------------------------
            # Phase 4: Change the FK.
            # ----------------------------------------------------------
            print_section(
                "PHASE 2: FOREIGN KEY MIGRATION"
            )

            migrate_constraint(
                connection
            )

            # ----------------------------------------------------------
            # Phase 5: Verify the new FK before commit.
            # ----------------------------------------------------------
            print_section(
                "PHASE 3: POST-MIGRATION VERIFICATION"
            )

            verify_new_constraint(
                connection
            )

            # ----------------------------------------------------------
            # Phase 6: Commit the complete migration.
            #
            # Why:
            # get_metastore_connection intentionally does not auto-commit.
            # Schema migration transaction control belongs here.
            # ----------------------------------------------------------
            connection.commit()

            print()
            print("Transaction commit: PASSED")

        except Exception as exc:

            # ----------------------------------------------------------
            # Roll back everything if any validation or migration step
            # fails.
            # ----------------------------------------------------------
            connection.rollback()

            print()
            print("Transaction rollback: EXECUTED")
            print(f"Migration failed: {exc}")

            # Re-raise the exception so the Python process exits with
            # a failure status.
            raise

    print()
    print("=" * 100)
    print("LOAD CONFIG FOREIGN KEY MIGRATION COMPLETED")
    print("Metadata model changed : ingest.load_config -> map.mapping_version")
    print("Legacy mapping_field   : UNCHANGED")
    print("Legacy mapping_source  : UNCHANGED")
    print("Legacy mapping_version : UNCHANGED")
    print("=" * 100)


if __name__ == "__main__":
    """
    Run the migration when this module is executed directly.
    """

    main()