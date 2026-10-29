import unittest

from app.runtime.schema_comparison import (
    assess_column_compatibility,
    compare_column_metadata,
)


def column(
    name: str,
    ordinal: int,
    **attributes: object,
) -> dict[str, object]:
    return {
        "column_name": name,
        "ordinal_position": ordinal,
        "data_type": "integer",
        "is_nullable": "NO",
        **attributes,
    }


class SchemaComparisonTests(unittest.TestCase):
    def test_matching_metadata_is_reported_as_equal(self) -> None:
        metadata = [
            column(
                "id",
                1,
                numeric_precision=32,
                numeric_scale=0,
            ),
            column(
                "amount",
                2,
                data_type="numeric",
                numeric_precision=12,
                numeric_scale=2,
                is_nullable="YES",
            ),
        ]

        self.assertEqual(compare_column_metadata(metadata, metadata), [])

    def test_default_differences_are_reported_separately_from_schema_match(
        self,
    ) -> None:
        source = [
            column(
                "order_id",
                1,
                column_default='nextval(\'"order_order_id_seq"\'::regclass)',
            ),
            column("balance", 2, data_type="numeric", column_default="0.00"),
            column(
                "last_updated",
                3,
                data_type="timestamp without time zone",
                column_default="CURRENT_TIMESTAMP",
            ),
        ]
        target = [
            column("order_id", 1, column_default=None),
            column("balance", 2, data_type="numeric", column_default=None),
            column(
                "last_updated",
                3,
                data_type="timestamp without time zone",
                column_default=None,
            ),
        ]

        result = assess_column_compatibility(
            source,
            target,
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        metadata_differences = compare_column_metadata(source, target)
        self.assertEqual(len(metadata_differences), 3)
        self.assertTrue(
            all("column_default differs" in item
                for item in metadata_differences)
        )
        self.assertEqual(result.schema_match_status, "Match")
        self.assertEqual(result.schema_differences, [])
        self.assertTrue(result.is_compatible)
        self.assertEqual(len(result.compatible_differences), 3)
        self.assertTrue(
            all(
                "defaults differ" in difference
                for difference in result.compatible_differences
            )
        )

    def test_reports_missing_and_extra_columns_without_reading_data(self) -> None:
        source = [column("id", 1), column("name", 2, data_type="text")]
        target = [column("id", 1), column("legacy", 2, data_type="text")]

        differences = compare_column_metadata(source, target)

        self.assertTrue(any("missing columns ['name']" in item for item in differences))
        self.assertTrue(any("extra columns ['legacy']" in item for item in differences))

    def test_reports_order_type_nullability_and_type_attribute_differences(self) -> None:
        source = [
            column(
                "id",
                1,
                data_type="numeric",
                numeric_precision=10,
                numeric_scale=2,
            ),
            column("name", 2, data_type="character varying", is_nullable="YES"),
        ]
        target = [
            column("name", 1, data_type="text", is_nullable="NO"),
            column(
                "id",
                2,
                data_type="numeric",
                numeric_precision=8,
                numeric_scale=2,
            ),
        ]

        differences = compare_column_metadata(source, target)

        self.assertTrue(any("column order differs" in item for item in differences))
        self.assertTrue(any("numeric_precision differs" in item for item in differences))
        self.assertTrue(any("data_type differs" in item for item in differences))
        self.assertTrue(any("is_nullable differs" in item for item in differences))

    def test_accepts_safe_postgres_target_widening_and_mapping_differences(
        self,
    ) -> None:
        source = [
            column(
                "customer_name",
                1,
                data_type="character varying",
                character_maximum_length=100,
                column_default=None,
            ),
            column(
                "amount",
                2,
                data_type="numeric",
                numeric_precision=10,
                numeric_scale=2,
                column_default="0.00",
            ),
        ]
        target = [
            column("amount", 1, data_type="numeric"),
            column("customer_name", 2, data_type="text"),
        ]

        result = assess_column_compatibility(
            source,
            target,
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        self.assertTrue(result.is_compatible)
        self.assertEqual(result.status, "Compatible with differences")
        self.assertTrue(
            any("column order differs" in item
                for item in result.compatible_differences)
        )
        self.assertTrue(
            any("safely widens" in item
                for item in result.compatible_differences)
        )
        self.assertTrue(
            any("unconstrained" in item
                for item in result.compatible_differences)
        )

    def test_blocks_narrow_types_and_stricter_target_nullability(self) -> None:
        source = [
            column(
                "name",
                1,
                data_type="character varying",
                character_maximum_length=100,
                is_nullable="YES",
            )
        ]
        target = [
            column(
                "name",
                1,
                data_type="character varying",
                character_maximum_length=50,
                is_nullable="NO",
            )
        ]

        result = assess_column_compatibility(
            source,
            target,
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        self.assertFalse(result.is_compatible)
        self.assertTrue(any("shorter than source" in item
                            for item in result.blocking_differences))
        self.assertTrue(any("nullable in source" in item
                            for item in result.blocking_differences))

    def test_accepts_wider_integer_target_with_same_connector(self) -> None:
        result = assess_column_compatibility(
            [column("id", 1, data_type="integer")],
            [column("id", 1, data_type="bigint")],
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        self.assertTrue(result.is_compatible)
        self.assertEqual(result.status, "Compatible with differences")
        self.assertTrue(
            any("safely widens" in item
                for item in result.compatible_differences)
        )

    def test_nullable_extra_target_column_is_compatible(self) -> None:
        result = assess_column_compatibility(
            [column("id", 1)],
            [
                column("id", 1),
                column(
                    "legacy_role",
                    2,
                    data_type="text",
                    is_nullable="YES",
                ),
            ],
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        self.assertTrue(result.is_compatible)
        self.assertEqual(result.status, "Compatible with differences")
        self.assertTrue(
            any("target-only column 'legacy_role'" in item
                for item in result.compatible_differences)
        )

    def test_required_extra_target_column_without_default_is_blocked(self) -> None:
        result = assess_column_compatibility(
            [column("id", 1)],
            [
                column("id", 1),
                column(
                    "required_legacy",
                    2,
                    data_type="text",
                    is_nullable="NO",
                    column_default=None,
                ),
            ],
            source_connector_code="POSTGRESQL_CONNECTOR",
            target_connector_code="POSTGRESQL_CONNECTOR",
        )

        self.assertFalse(result.is_compatible)
        self.assertEqual(result.status, "Mismatch")
        self.assertTrue(
            any("cannot safely be omitted" in item
                for item in result.blocking_differences)
        )


if __name__ == "__main__":
    unittest.main()
