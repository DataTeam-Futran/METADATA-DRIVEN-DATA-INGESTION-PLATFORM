"""
Customer Target Schema Planning
================================

Purpose
-------
This script creates a READ-ONLY target schema plan for the customer
full-load ingestion POC.

The script does NOT:
    - create the target table
    - modify metadata
    - insert mapping records
    - update schema versions
    - execute CREATE TABLE

It only reads existing metadata and generates the target DDL
that will be used in the next development stage.

Flow
----
Source Dataset
      |
      v
Source Schema Version
      |
      v
Source Dataset Fields
      |
      v
Target Dataset
      |
      v
Target Dataset Binding
      |
      v
Target Schema Plan
      |
      v
Proposed CREATE TABLE statement
"""

from __future__ import annotations

from dataclasses import dataclass

from app.db.metastore import get_metastore_connection


# ---------------------------------------------------------------------------
# POC metadata identifiers
# ---------------------------------------------------------------------------
# These identifiers already exist in the metadata database.
#
# They are kept together here only for this POC script.
# In the production runtime, these values should come from a mapping
# or execution request rather than being hardcoded.
# ---------------------------------------------------------------------------

SOURCE_DATASET_ID = 7
SOURCE_SCHEMA_VERSION_ID = 6

TARGET_DATASET_ID = 8
TARGET_BINDING_ID = 8


# ---------------------------------------------------------------------------
# Target field model
# ---------------------------------------------------------------------------
# This object represents one field in the target schema plan.
#
# Keeping the planning result in a typed structure makes the next stages
# easier because the same plan can later be passed to DDL generation
# and physical target creation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetFieldPlan:
    """
    Represents one planned target column.

    source_field_name
        Name of the source column.

    target_field_name
        Name that will be used in the target table.

    source_datatype
        Datatype captured from the source schema.

    target_datatype
        Datatype planned for the target database.

    ordinal_position
        Original source column order.

    is_nullable
        Whether NULL is allowed in the target column.
    """

    source_field_name: str
    target_field_name: str
    source_datatype: str
    target_datatype: str
    ordinal_position: int
    is_nullable: bool


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------
# Target schema/table names come from metadata.
#
# They must still be validated before being placed into SQL because SQL
# identifiers cannot be passed as normal parameterized values.
# ---------------------------------------------------------------------------


def quote_identifier(identifier: str) -> str:
    """
    Safely quote a PostgreSQL identifier.

    PostgreSQL identifiers use double quotes.

    Example:
        warehouse -> "warehouse"
        customer_target -> "customer_target"
    """

    if not identifier:
        raise ValueError("SQL identifier cannot be empty.")

    # Reject embedded null characters because they are never valid
    # PostgreSQL identifiers and could indicate malformed metadata.
    if "\x00" in identifier:
        raise ValueError("SQL identifier contains an invalid null character.")

    # Escape an embedded double quote according to PostgreSQL rules.
    escaped_identifier = identifier.replace('"', '""')

    return f'"{escaped_identifier}"'


# ---------------------------------------------------------------------------
# Read source metadata
# ---------------------------------------------------------------------------


def get_source_metadata(connection):
    """
    Read the source dataset, schema version, and source fields.

    No metadata is modified.
    """

    query = """
        SELECT
            d.dataset_id,
            d.tenant_id,
            d.project_id,
            d.dataset_code,
            d.dataset_name,
            d.dataset_role_code,
            d.object_type_code,
            d.status_code,
            sv.schema_version_id,
            sv.version_no,
            sv.schema_hash,
            sv.is_current
        FROM catalog.dataset AS d
        INNER JOIN catalog.dataset_schema_version AS sv
            ON sv.dataset_id = d.dataset_id
        WHERE d.dataset_id = %s
          AND sv.schema_version_id = %s
          AND sv.is_current = TRUE
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                SOURCE_DATASET_ID,
                SOURCE_SCHEMA_VERSION_ID,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            "Source dataset/schema version could not be found."
        )

    return row


def get_source_fields(connection):
    """
    Read all fields belonging to the selected source schema version.

    Fields are returned in their original ordinal order.
    """

    query = """
        SELECT
            field_id,
            ordinal_no,
            field_name,
            field_name_normalized,
            native_datatype_id,
            source_datatype_text,
            length_value,
            precision_value,
            scale_value,
            is_nullable,
            default_expression,
            is_identity,
            is_generated
        FROM catalog.dataset_field
        WHERE schema_version_id = %s
        ORDER BY ordinal_no;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (SOURCE_SCHEMA_VERSION_ID,),
        )

        rows = cursor.fetchall()

    if not rows:
        raise LookupError(
            "No fields were found for the source schema version."
        )

    return rows


# ---------------------------------------------------------------------------
# Read target metadata
# ---------------------------------------------------------------------------


def get_target_metadata(connection):
    """
    Read and validate the target dataset and target binding.

    This confirms that the target location is already registered
    in metadata before generating the target DDL.
    """

    query = """
        SELECT
            d.dataset_id,
            d.tenant_id,
            d.project_id,
            d.dataset_code,
            d.dataset_name,
            d.dataset_role_code,
            d.object_type_code,
            d.layer_code,
            d.status_code,

            b.dataset_binding_id,
            b.environment_id,
            b.connection_id,
            b.catalog_name,
            b.schema_name,
            b.object_name,
            b.object_name_normalized,
            b.status_code

        FROM catalog.dataset AS d
        INNER JOIN catalog.dataset_binding AS b
            ON b.dataset_id = d.dataset_id

        WHERE d.dataset_id = %s
          AND b.dataset_binding_id = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (
                TARGET_DATASET_ID,
                TARGET_BINDING_ID,
            ),
        )

        row = cursor.fetchone()

    if row is None:
        raise LookupError(
            "Target dataset/binding could not be found."
        )

    return row


# ---------------------------------------------------------------------------
# Resolve target datatype
# ---------------------------------------------------------------------------
# For the first POC we are dealing with PostgreSQL -> PostgreSQL.
#
# Therefore, when the source native datatype is already compatible with
# PostgreSQL, we preserve the source native datatype.
#
# This is deliberately limited to the current same-platform POC.
#
# Later, this function will be replaced by the metadata-driven datatype
# resolution engine using dtype.datatype_mapping_set and
# dtype.datatype_mapping_rule.
# ---------------------------------------------------------------------------


def resolve_target_datatype(
    source_datatype: str,
    length_value,
    precision_value,
    scale_value,
) -> str:
    """
    Resolve the target PostgreSQL datatype for the current POC.

    The function preserves the source PostgreSQL native datatype.

    Length/precision/scale are included in the function signature because
    they will be required by the generic datatype resolver later.
    """

    normalized_type = source_datatype.strip().lower()

    # -----------------------------------------------------------------------
    # Character varying
    # -----------------------------------------------------------------------
    # If a source length is available, preserve it.
    #
    # If no length exists, PostgreSQL allows unbounded character varying.
    # -----------------------------------------------------------------------

    if normalized_type == "character varying":
        if length_value is not None:
            return f"character varying({int(length_value)})"

        return "character varying"

    # -----------------------------------------------------------------------
    # Numeric
    # -----------------------------------------------------------------------
    # Preserve precision and scale when available.
    # -----------------------------------------------------------------------

    if normalized_type == "numeric":
        if precision_value is not None and scale_value is not None:
            return f"numeric({int(precision_value)},{int(scale_value)})"

        if precision_value is not None:
            return f"numeric({int(precision_value)})"

        return "numeric"

    # -----------------------------------------------------------------------
    # Other PostgreSQL native datatypes
    # -----------------------------------------------------------------------
    # For the current PostgreSQL -> PostgreSQL POC, preserve the native
    # datatype text.
    # -----------------------------------------------------------------------

    return normalized_type


# ---------------------------------------------------------------------------
# Build target schema plan
# ---------------------------------------------------------------------------


def build_target_plan(source_fields) -> list[TargetFieldPlan]:
    """
    Convert source catalog fields into target field plans.

    No database changes are performed here.
    """

    target_plan: list[TargetFieldPlan] = []

    for field in source_fields:
        (
            field_id,
            ordinal_no,
            field_name,
            field_name_normalized,
            native_datatype_id,
            source_datatype_text,
            length_value,
            precision_value,
            scale_value,
            is_nullable,
            default_expression,
            is_identity,
            is_generated,
        ) = field

        if not field_name:
            raise ValueError(
                f"Source field ID {field_id} has no field name."
            )

        if not source_datatype_text:
            raise ValueError(
                f"Source field '{field_name}' has no datatype."
            )

        target_datatype = resolve_target_datatype(
            source_datatype=source_datatype_text,
            length_value=length_value,
            precision_value=precision_value,
            scale_value=scale_value,
        )

        target_plan.append(
            TargetFieldPlan(
                source_field_name=field_name,
                target_field_name=field_name,
                source_datatype=source_datatype_text,
                target_datatype=target_datatype,
                ordinal_position=ordinal_no,
                is_nullable=bool(is_nullable),
            )
        )

    return target_plan


# ---------------------------------------------------------------------------
# Generate target DDL
# ---------------------------------------------------------------------------
# This function only generates a SQL string.
#
# It DOES NOT execute the SQL.
# ---------------------------------------------------------------------------


def generate_create_table_ddl(
    schema_name: str,
    table_name: str,
    target_plan: list[TargetFieldPlan],
) -> str:
    """
    Generate the CREATE TABLE statement for the planned target schema.
    """

    if not target_plan:
        raise ValueError(
            "Cannot generate target DDL without target fields."
        )

    column_definitions = []

    for field in target_plan:
        nullable_clause = "" if field.is_nullable else " NOT NULL"

        column_definitions.append(
            "    "
            f"{quote_identifier(field.target_field_name)} "
            f"{field.target_datatype}"
            f"{nullable_clause}"
        )

    columns_sql = ",\n".join(column_definitions)

    return (
        f"CREATE TABLE {quote_identifier(schema_name)}."
        f"{quote_identifier(table_name)} (\n"
        f"{columns_sql}\n"
        ");"
    )


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


def main() -> None:
    """
    Execute the read-only target schema planning process.
    """

    print("=" * 72)
    print("CUSTOMER TARGET SCHEMA PLANNING")
    print("=" * 72)

    print()
    print("SOURCE METADATA")
    print("-" * 72)

    with get_metastore_connection() as connection:

        # ---------------------------------------------------------------
        # Read source dataset and schema version.
        # ---------------------------------------------------------------

        source_metadata = get_source_metadata(connection)

        (
            source_dataset_id,
            source_tenant_id,
            source_project_id,
            source_dataset_code,
            source_dataset_name,
            source_dataset_role,
            source_object_type,
            source_status,
            source_schema_version_id,
            source_version_no,
            source_schema_hash,
            source_is_current,
        ) = source_metadata

        print(f"Dataset ID        : {source_dataset_id}")
        print(f"Dataset Code      : {source_dataset_code}")
        print(f"Dataset Name      : {source_dataset_name}")
        print(f"Dataset Role      : {source_dataset_role}")
        print(f"Object Type       : {source_object_type}")
        print(f"Schema Version ID  : {source_schema_version_id}")
        print(f"Schema Version No  : {source_version_no}")
        print(f"Schema Hash        : {source_schema_hash}")
        print(f"Current            : {source_is_current}")

        if source_status != "ACTIVE":
            raise ValueError(
                f"Source dataset is not ACTIVE: {source_status}"
            )

        if not source_is_current:
            raise ValueError(
                "Selected source schema version is not CURRENT."
            )

        # ---------------------------------------------------------------
        # Read source fields.
        # ---------------------------------------------------------------

        source_fields = get_source_fields(connection)

        print()
        print("SOURCE FIELDS")
        print("-" * 72)

        for field in source_fields:
            (
                field_id,
                ordinal_no,
                field_name,
                field_name_normalized,
                native_datatype_id,
                source_datatype_text,
                length_value,
                precision_value,
                scale_value,
                is_nullable,
                default_expression,
                is_identity,
                is_generated,
            ) = field

            print(
                f"{ordinal_no}. "
                f"{field_name} | "
                f"{source_datatype_text} | "
                f"Nullable={is_nullable}"
            )

        # ---------------------------------------------------------------
        # Read target metadata.
        # ---------------------------------------------------------------

        target_metadata = get_target_metadata(connection)

        (
            target_dataset_id,
            target_tenant_id,
            target_project_id,
            target_dataset_code,
            target_dataset_name,
            target_dataset_role,
            target_object_type,
            target_layer,
            target_status,
            target_binding_id,
            target_environment_id,
            target_connection_id,
            target_catalog_name,
            target_schema_name,
            target_object_name,
            target_object_name_normalized,
            target_binding_status,
        ) = target_metadata

        print()
        print("TARGET METADATA")
        print("-" * 72)

        print(f"Dataset ID        : {target_dataset_id}")
        print(f"Dataset Code      : {target_dataset_code}")
        print(f"Dataset Name      : {target_dataset_name}")
        print(f"Dataset Role      : {target_dataset_role}")
        print(f"Object Type       : {target_object_type}")
        print(f"Layer             : {target_layer}")
        print(f"Binding ID        : {target_binding_id}")
        print(f"Environment ID    : {target_environment_id}")
        print(f"Connection ID     : {target_connection_id}")
        print(f"Database          : {target_catalog_name}")
        print(f"Schema            : {target_schema_name}")
        print(f"Object            : {target_object_name}")
        print(f"Status            : {target_status}")
        print(f"Binding Status    : {target_binding_status}")

        if target_status != "ACTIVE":
            raise ValueError(
                f"Target dataset is not ACTIVE: {target_status}"
            )

        if target_binding_status != "ACTIVE":
            raise ValueError(
                f"Target binding is not ACTIVE: {target_binding_status}"
            )

        if target_dataset_role != "TARGET":
            raise ValueError(
                f"Expected TARGET dataset but found: "
                f"{target_dataset_role}"
            )

        # ---------------------------------------------------------------
        # Build target field plan.
        # ---------------------------------------------------------------

        target_plan = build_target_plan(source_fields)

        print()
        print("TARGET SCHEMA PLAN")
        print("-" * 72)

        print(
            f"{'SOURCE FIELD':<22}"
            f"{'TARGET FIELD':<22}"
            f"{'SOURCE TYPE':<25}"
            f"TARGET TYPE"
        )

        print("-" * 95)

        for field in target_plan:
            print(
                f"{field.source_field_name:<22}"
                f"{field.target_field_name:<22}"
                f"{field.source_datatype:<25}"
                f"{field.target_datatype}"
            )

        # ---------------------------------------------------------------
        # Generate DDL.
        #
        # IMPORTANT:
        # The generated SQL is printed only.
        # It is NOT executed.
        # ---------------------------------------------------------------

        ddl = generate_create_table_ddl(
            schema_name=target_schema_name,
            table_name=target_object_name,
            target_plan=target_plan,
        )

        print()
        print("PROPOSED TARGET DDL")
        print("-" * 72)
        print(ddl)

    print()
    print("=" * 72)
    print("TARGET SCHEMA PLANNING COMPLETED")
    print("=" * 72)
    print()
    print("IMPORTANT: No database changes were made.")
    print("The DDL above is only the proposed physical target schema.")


if __name__ == "__main__":
    main()