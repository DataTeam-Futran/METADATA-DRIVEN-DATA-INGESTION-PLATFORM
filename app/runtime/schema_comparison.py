"""Metadata-only comparison of source and target table schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SchemaCompatibility:
    """Separate safe-to-load metadata differences from blocking drift."""

    blocking_differences: list[str]
    compatible_differences: list[str]
    schema_differences: list[str]

    @property
    def is_compatible(self) -> bool:
        return not self.blocking_differences

    @property
    def status(self) -> str:
        if self.blocking_differences:
            return "Mismatch"
        if self.compatible_differences:
            return "Compatible with differences"
        return "Match"

    @property
    def schema_match_status(self) -> str:
        """Report structural equality; default behavior is reported separately."""
        return "Match" if not self.schema_differences else "Mismatch"


_COMPARABLE_ATTRIBUTES = (
    "data_type",
    "character_maximum_length",
    "numeric_precision",
    "numeric_scale",
    "datetime_precision",
    "is_nullable",
    "column_default",
    "is_identity",
    "is_generated",
)


def compare_column_metadata(
    source_columns: list[dict[str, Any]],
    target_columns: list[dict[str, Any]],
    *,
    include_defaults: bool = True,
) -> list[str]:
    """Return metadata differences without reading any table data.

    Set ``include_defaults=False`` for structural schema comparison. Defaults
    affect behavior but do not change column shape, and are assessed
    separately for load compatibility.
    """

    def ordered(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            columns,
            key=lambda column: column.get(
                "ordinal_position",
                column.get("ordinal_no", 0),
            ),
        )

    source = ordered(source_columns)
    target = ordered(target_columns)
    differences: list[str] = []
    source_names = [column.get("column_name") for column in source]
    target_names = [column.get("column_name") for column in target]

    if source_names != target_names:
        missing = [name for name in source_names if name not in target_names]
        extra = [name for name in target_names if name not in source_names]
        if missing:
            differences.append(f"target is missing columns {missing}")
        if extra:
            differences.append(f"target has extra columns {extra}")
        if not missing and not extra:
            differences.append(
                "column order differs "
                f"(source={source_names}, target={target_names})"
            )

    target_by_name = {
        column.get("column_name"): column
        for column in target
        if column.get("column_name") is not None
    }

    for source_column in source:
        name = source_column.get("column_name")
        target_column = target_by_name.get(name)
        if target_column is None:
            continue

        attributes = _COMPARABLE_ATTRIBUTES
        if not include_defaults:
            attributes = tuple(
                attribute
                for attribute in attributes
                if attribute != "column_default"
            )
        for attribute in attributes:
            source_value = _normalize_attribute(
                attribute,
                source_column.get(attribute),
            )
            target_value = _normalize_attribute(
                attribute,
                target_column.get(attribute),
            )
            if source_value != target_value:
                differences.append(
                    f"column {name!r} {attribute} differs "
                    f"(source={source_value!r}, target={target_value!r})"
                )

    return differences


def assess_column_compatibility(
    source_columns: list[dict[str, Any]],
    target_columns: list[dict[str, Any]],
    *,
    source_connector_code: str,
    target_connector_code: str,
) -> SchemaCompatibility:
    """Assess whether the target can safely receive explicit source columns.

    Column order and defaults do not affect this loader: it writes every
    source value using an explicit, name-based target column list. Wider
    target types are accepted only for the same connector dialect. Missing
    source columns, narrowing, generated source-mapped target columns,
    and stricter target nullability remain blocking differences. Extra target
    columns are compatible only when inserts can omit them safely.
    """

    def ordered(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            columns,
            key=lambda column: column.get(
                "ordinal_position",
                column.get("ordinal_no", 0),
            ),
        )

    source = ordered(source_columns)
    target = ordered(target_columns)
    blocking: list[str] = []
    compatible: list[str] = []
    source_names = [column.get("column_name") for column in source]
    target_names = [column.get("column_name") for column in target]
    source_name_set = set(source_names)
    target_name_set = set(target_names)
    same_dialect = (
        source_connector_code.strip().casefold()
        == target_connector_code.strip().casefold()
    )

    missing = [name for name in source_names if name not in target_name_set]
    extra = [name for name in target_names if name not in source_name_set]
    if missing:
        blocking.append(f"target is missing columns {missing}")
    if extra:
        source_target_columns = [
            column
            for column in target
            if column.get("column_name") in extra
        ]
        for target_column in source_target_columns:
            name = target_column.get("column_name")
            nullable = _nullable(target_column.get("is_nullable"))
            default = target_column.get("column_default")
            has_default = (
                isinstance(default, str)
                and bool(default.strip())
                and default.strip().casefold() != "null"
            )
            is_identity = _nullable(target_column.get("is_identity")) is True
            generated_value = str(
                target_column.get("is_generated", "NEVER")
            ).strip().upper() not in {"", "NEVER", "NO", "FALSE", "0"}

            if nullable is True or has_default or is_identity or generated_value:
                compatible.append(
                    f"target-only column {name!r} is omitted from the "
                    "explicit source-column insert; its target nullability, "
                    "default, or generation behavior permits omission"
                )
            else:
                blocking.append(
                    f"target-only column {name!r} cannot safely be omitted "
                    "because it is NOT NULL or its nullability/default "
                    "metadata is unavailable"
                )

    if not missing and not extra and source_names != target_names:
        compatible.append(
            "column order differs; values are inserted by explicit column name "
            f"(source={source_names}, target={target_names})"
        )

    target_by_name = {
        column.get("column_name"): column
        for column in target
        if column.get("column_name") is not None
    }

    for source_column in source:
        name = source_column.get("column_name")
        target_column = target_by_name.get(name)
        if target_column is None:
            continue

        type_differences, type_warnings = _compare_type_capacity(
            source_column,
            target_column,
            same_dialect=same_dialect,
            target_connector_code=target_connector_code,
        )
        blocking.extend(
            f"column {name!r} {difference}" for difference in type_differences
        )
        compatible.extend(
            f"column {name!r} {warning}" for warning in type_warnings
        )

        source_nullable = _nullable(source_column.get("is_nullable"))
        target_nullable = _nullable(target_column.get("is_nullable"))
        if source_nullable is True and target_nullable is False:
            blocking.append(
                f"column {name!r} is nullable in source but NOT NULL in target"
            )
        elif source_nullable is False and target_nullable is True:
            compatible.append(
                f"column {name!r} is nullable in target but NOT NULL in source"
            )
        elif source_nullable is None or target_nullable is None:
            if source_nullable != target_nullable:
                blocking.append(
                    f"column {name!r} nullability metadata is incomplete"
                )

        source_default = _normalize_attribute(
            "column_default",
            source_column.get("column_default"),
        )
        target_default = _normalize_attribute(
            "column_default",
            target_column.get("column_default"),
        )
        if source_default != target_default:
            compatible.append(
                f"column {name!r} defaults differ; explicit source values "
                "are inserted"
            )

        target_identity = _nullable(target_column.get("is_identity"))
        target_generated = str(
            target_column.get("is_generated", "NEVER")
        ).strip().upper() not in {"", "NEVER", "NO", "FALSE", "0"}
        if target_identity is True or target_generated:
            blocking.append(
                f"column {name!r} is identity/generated in target and may "
                "reject explicit source values"
            )

    return SchemaCompatibility(
        blocking_differences=blocking,
        compatible_differences=compatible,
        schema_differences=compare_column_metadata(
            source_columns,
            target_columns,
            include_defaults=False,
        ),
    )


def _compare_type_capacity(
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    same_dialect: bool,
    target_connector_code: str,
) -> tuple[list[str], list[str]]:
    source_type = _normalize_type(source.get("data_type"))
    target_type = _normalize_type(target.get("data_type"))
    blocking: list[str] = []
    compatible: list[str] = []

    character_types = {"varchar", "char", "text", "nvarchar", "nchar"}
    numeric_types = {"numeric"}
    integer_ranks = {"smallint": 1, "integer": 2, "bigint": 3}
    same_family = (
        source_type == target_type
        or source_type in character_types
        and target_type in character_types
        or source_type in numeric_types
        and target_type in numeric_types
        or source_type in integer_ranks
        and target_type in integer_ranks
    )
    if not same_family:
        blocking.append(
            f"data_type is not compatible "
            f"(source={source.get('data_type')!r}, "
            f"target={target.get('data_type')!r})"
        )
        return blocking, compatible

    if source_type != target_type:
        can_widen_character = (
            same_dialect
            and source_type in {"varchar", "char"}
            and target_type == "text"
        )
        can_widen_integer = (
            same_dialect
            and source_type in integer_ranks
            and target_type in integer_ranks
            and integer_ranks[target_type] > integer_ranks[source_type]
        )
        if not can_widen_character and not can_widen_integer:
            blocking.append(
                f"data_type differs "
                f"(source={source.get('data_type')!r}, "
                f"target={target.get('data_type')!r})"
            )
            return blocking, compatible
        compatible.append(
            (
                f"target type {target.get('data_type')!r} safely widens "
                f"source type {source.get('data_type')!r}"
            )
        )

    if source_type in character_types and target_type in character_types:
        source_length = source.get("character_maximum_length")
        target_length = target.get("character_maximum_length")
        target_unbounded = (
            target_type == "text"
            or target_length == -1
            or (
                same_dialect
                and target_type == "varchar"
                and target_length is None
            )
        )
        if target_unbounded:
            if source_length != target_length:
                compatible.append(
                    "target character capacity is unbounded and accepts the "
                    f"source length ({source_length!r})"
                )
        elif source_length is None:
            if target_length is not None:
                blocking.append(
                    "source character length is unbounded/unknown but "
                    f"target length is {target_length!r}"
                )
        elif target_length is None:
            blocking.append("target character length metadata is unavailable")
        elif target_length < source_length:
            blocking.append(
                f"target character length {target_length} is shorter than "
                f"source length {source_length}"
            )
        elif target_length > source_length:
            compatible.append(
                f"target character length {target_length} is wider than "
                f"source length {source_length}"
            )

    if source_type in numeric_types:
        source_precision = source.get("numeric_precision")
        source_scale = source.get("numeric_scale")
        target_precision = target.get("numeric_precision")
        target_scale = target.get("numeric_scale")
        postgres_unbounded_numeric = (
            target_connector_code.strip().casefold()
            == "postgresql_connector"
            and target_precision is None
            and target_scale is None
        )
        if postgres_unbounded_numeric and source_precision is not None:
            compatible.append(
                "target NUMERIC is unconstrained and accepts source "
                f"precision/scale ({source_precision}, {source_scale})"
            )
        elif (
            isinstance(source_precision, int)
            and isinstance(source_scale, int)
            and isinstance(target_precision, int)
            and isinstance(target_scale, int)
        ):
            source_integer_digits = source_precision - source_scale
            target_integer_digits = target_precision - target_scale
            if (
                target_scale < source_scale
                or target_integer_digits < source_integer_digits
            ):
                blocking.append(
                    "target numeric precision/scale is narrower "
                    f"(source={source_precision},{source_scale}, "
                    f"target={target_precision},{target_scale})"
                )
            elif (
                target_precision != source_precision
                or target_scale != source_scale
            ):
                compatible.append(
                    "target numeric precision/scale is wider "
                    f"(source={source_precision},{source_scale}, "
                    f"target={target_precision},{target_scale})"
                )
        elif (source_precision, source_scale) != (
            target_precision,
            target_scale,
        ):
            blocking.append(
                "numeric precision/scale metadata is incomplete or "
                f"incompatible (source={source_precision},{source_scale}, "
                f"target={target_precision},{target_scale})"
            )

    source_datetime_precision = source.get("datetime_precision")
    target_datetime_precision = target.get("datetime_precision")
    if source_datetime_precision != target_datetime_precision:
        if (
            isinstance(source_datetime_precision, int)
            and isinstance(target_datetime_precision, int)
            and target_datetime_precision >= source_datetime_precision
        ):
            compatible.append(
                "target temporal precision is at least as precise as source "
                f"({target_datetime_precision} >= {source_datetime_precision})"
            )
        elif source_datetime_precision is not None or target_datetime_precision is not None:
            blocking.append(
                "datetime precision differs or is incomplete "
                f"(source={source_datetime_precision!r}, "
                f"target={target_datetime_precision!r})"
            )

    return blocking, compatible


def _normalize_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().casefold().split())
    aliases = {
        "character varying": "varchar",
        "varchar": "varchar",
        "character": "char",
        "char": "char",
        "integer": "integer",
        "int": "integer",
        "int4": "integer",
        "smallint": "smallint",
        "int2": "smallint",
        "bigint": "bigint",
        "int8": "bigint",
        "decimal": "numeric",
        "numeric": "numeric",
    }
    return aliases.get(normalized, normalized)


def _nullable(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return str(value).strip().upper() in {"YES", "TRUE", "1"}


def _normalize_attribute(attribute: str, value: Any) -> Any:
    if attribute == "is_nullable":
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        return str(value).strip().upper() in {"YES", "TRUE", "1"}

    if attribute == "data_type":
        if value is None:
            return None
        return " ".join(str(value).strip().casefold().split())

    if attribute == "column_default":
        if value is None:
            return None
        return " ".join(str(value).strip().casefold().split())

    return value
