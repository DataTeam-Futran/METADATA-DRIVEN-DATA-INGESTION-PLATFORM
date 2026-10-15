import re

from app.connectors.base import BaseConnector
from app.incremental.models import ColumnMetadata
from app.runtime.object_resolver import RuntimeObject


class SchemaValidationError(ValueError):
    pass


def quote_identifier(identifier: str) -> str:
    if not identifier or not identifier.strip():
        raise ValueError("SQL identifiers must not be empty.")
    return '"' + identifier.strip().replace('"', '""') + '"'


def discover_columns(
    connector: BaseConnector,
    physical_object: RuntimeObject,
) -> list[ColumnMetadata]:
    if not physical_object.schema_name:
        raise SchemaValidationError("Physical schema name is missing.")
    connection = connector._require_connection()
    query = """
        SELECT
            a.attname,
            format_type(a.atttypid, a.atttypmod),
            NOT a.attnotnull,
            pg_get_expr(d.adbin, d.adrelid),
            a.attnum,
            EXISTS (
                SELECT 1
                FROM pg_index AS i
                WHERE i.indrelid = a.attrelid
                  AND i.indisprimary
                  AND a.attnum = ANY(i.indkey)
            )
        FROM pg_class AS t
        INNER JOIN pg_namespace AS n ON n.oid = t.relnamespace
        INNER JOIN pg_attribute AS a ON a.attrelid = t.oid
        LEFT JOIN pg_attrdef AS d
          ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        WHERE n.nspname = %s
          AND t.relname = %s
          AND t.relkind IN ('r', 'p')
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum;
    """
    with connection.cursor() as cursor:
        cursor.execute(
            query,
            (physical_object.schema_name, physical_object.object_name),
        )
        rows = cursor.fetchall()
    if not rows:
        raise SchemaValidationError(
            f"Table {physical_object.schema_name}."
            f"{physical_object.object_name} was not found or has no columns."
        )
    return [
        ColumnMetadata(
            name=row[0],
            data_type=row[1],
            nullable=row[2],
            default_expression=row[3],
            ordinal=row[4],
            is_primary_key=row[5],
        )
        for row in rows
    ]


def build_incremental_query(
    physical_object: RuntimeObject,
    columns: tuple[str, ...] | list[str],
    watermark_column: str,
) -> str:
    if not columns:
        raise ValueError("At least one source column must be selected.")
    if watermark_column not in columns:
        raise SchemaValidationError(
            f"Watermark column {watermark_column!r} is not selected."
        )
    if not physical_object.schema_name:
        raise SchemaValidationError("Source schema name is missing.")
    selected_columns = ", ".join(quote_identifier(name) for name in columns)
    return (
        f"SELECT {selected_columns} "
        f"FROM {quote_identifier(physical_object.schema_name)}."
        f"{quote_identifier(physical_object.object_name)} "
        f"WHERE {quote_identifier(watermark_column)} > %s "
        f"AND {quote_identifier(watermark_column)} <= %s "
        f"ORDER BY {quote_identifier(watermark_column)}"
    )


def compare_schemas(
    source: list[ColumnMetadata],
    target: list[ColumnMetadata],
    watermark_column: str,
    require_primary_key: bool = True,
) -> list[str]:
    if watermark_column not in {column.name for column in source}:
        raise SchemaValidationError(
            f"Required source watermark column {watermark_column!r} is missing."
        )
    source_by_name = {column.name: column for column in source}
    target_by_name = {column.name: column for column in target}
    differences: list[str] = []
    for name in sorted(source_by_name.keys() - target_by_name.keys()):
        differences.append(f"Target is missing source column {name!r}.")
    for name in sorted(target_by_name.keys() - source_by_name.keys()):
        differences.append(f"Unexpected target column {name!r}.")
    for name in sorted(source_by_name.keys() & target_by_name.keys()):
        source_column = source_by_name[name]
        target_column = target_by_name[name]
        if source_column.data_type.lower() != target_column.data_type.lower():
            differences.append(
                f"Column {name!r} type mismatch: source "
                f"{source_column.data_type}, target {target_column.data_type}."
            )
        if source_column.nullable != target_column.nullable:
            differences.append(f"Column {name!r} nullability differs.")
        if source_column.is_primary_key != target_column.is_primary_key:
            differences.append(f"Column {name!r} primary-key membership differs.")
    source_keys = tuple(c.name for c in source if c.is_primary_key)
    target_keys = tuple(c.name for c in target if c.is_primary_key)
    if require_primary_key and not source_keys:
        raise SchemaValidationError("Source table has no primary key for duplicate handling.")
    if require_primary_key and source_keys != target_keys:
        differences.append(
            f"Primary key differs: source={source_keys}, target={target_keys}."
        )
    return differences


def add_missing_target_columns(
    target_connector: BaseConnector,
    target_object: RuntimeObject,
    source_columns: list[ColumnMetadata],
    target_columns: list[ColumnMetadata],
) -> int:
    target_names = {column.name for column in target_columns}
    missing = [column for column in source_columns if column.name not in target_names]
    if not missing:
        return 0
    supported_type = re.compile(
        r"^(smallint|integer|bigint|real|double precision|boolean|text|"
        r"character varying(?:\([0-9]+\))?|character(?:\([0-9]+\))?|"
        r"numeric(?:\([0-9]+(?:,[0-9]+)?\))?|date|time(?:\([0-9]+\))?(?: with time zone| without time zone)?|"
        r"timestamp(?:\([0-9]+\))?(?: with time zone| without time zone)?|uuid|json|jsonb|bytea)$",
        re.IGNORECASE,
    )
    connection = target_connector._require_connection()
    with connection.cursor() as cursor:
        for column in missing:
            if not supported_type.fullmatch(column.data_type):
                raise SchemaValidationError(
                    f"Cannot safely add column {column.name!r} with type "
                    f"{column.data_type!r}."
                )
            cursor.execute(
                f"ALTER TABLE {quote_identifier(target_object.schema_name or '')}."
                f"{quote_identifier(target_object.object_name)} "
                f"ADD COLUMN {quote_identifier(column.name)} {column.data_type};"
            )
    return len(missing)