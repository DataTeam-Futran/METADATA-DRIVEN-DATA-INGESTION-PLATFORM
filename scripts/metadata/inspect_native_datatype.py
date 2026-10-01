"""
Inspect dtype.native_datatype
=============================

Purpose
-------
This script displays the actual columns available in the
dtype.native_datatype metadata table.

Why this is needed
------------------
The metadata schema is the source of truth for the ingestion platform.

We must not assume column names such as:
    - datatype_code
    - datatype_name
    - native_type_name

Instead, we inspect the actual database definition before building
the datatype validation logic.

This script is READ-ONLY.
It does not modify any metadata.
"""

from app.db.metastore import get_metastore_connection


def main() -> None:
    """
    Display the actual structure of dtype.native_datatype.
    """

    print("=" * 72)
    print("NATIVE DATATYPE METADATA INSPECTION")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Query PostgreSQL's information_schema.
    #
    # information_schema.columns gives us the actual column names and
    # PostgreSQL data types defined in the metadata database.
    # ------------------------------------------------------------------

    query = """
        SELECT
            ordinal_position,
            column_name,
            data_type,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'dtype'
          AND table_name = 'native_datatype'
        ORDER BY ordinal_position;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)

            rows = cursor.fetchall()

    if not rows:
        raise LookupError(
            "Table dtype.native_datatype was not found "
            "or contains no column metadata."
        )

    print()
    print("dtype.native_datatype COLUMNS")
    print("-" * 72)

    for row in rows:
        (
            ordinal_position,
            column_name,
            data_type,
            is_nullable,
        ) = row

        print(
            f"{ordinal_position}. "
            f"{column_name} | "
            f"{data_type} | "
            f"Nullable={is_nullable}"
        )

    print()
    print("=" * 72)
    print("INSPECTION COMPLETED")
    print("=" * 72)
    print()
    print("No metadata changes were made.")


if __name__ == "__main__":
    main()