
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.core.exceptions import SchemaValidationError
from app.runtime.full_load_executor import FullLoadExecutor


class TestFullLoadDatatypeValidation(unittest.TestCase):

    def setUp(self):
        self.source_connector = Mock()
        self.target_connector = Mock()

        self.source_object = SimpleNamespace(
            schema_name="public",
            object_name="source_table",
        )

        self.target_object = SimpleNamespace(
            schema_name="dbo",
            object_name="target_table",
        )

    def validate(self):
        FullLoadExecutor._validate_physical_schema(
            source_connector=self.source_connector,
            target_connector=self.target_connector,
            source_object=self.source_object,
            target_object=self.target_object,
            source_columns=["customer_id"],
            target_columns=["customer_id"],
        )

    def test_compatible_integer_types_are_accepted(self):
        self.source_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "integer",
            }
        ]

        self.target_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "int",
            }
        ]

        self.validate()

    def test_incompatible_text_to_integer_is_rejected(self):
        self.source_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "text",
            }
        ]

        self.target_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "int",
            }
        ]

        with self.assertRaisesRegex(
            SchemaValidationError,
            "datatype mismatch",
        ):
            self.validate()

    def test_missing_source_datatype_is_rejected(self):
        self.source_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": None,
            }
        ]

        self.target_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "int",
            }
        ]

        with self.assertRaisesRegex(
            SchemaValidationError,
            "Source datatype metadata is missing",
        ):
            self.validate()

    def test_missing_target_datatype_is_rejected(self):
        self.source_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "integer",
            }
        ]

        self.target_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "",
            }
        ]

        with self.assertRaisesRegex(
            SchemaValidationError,
            "Target datatype metadata is missing",
        ):
            self.validate()

    def test_unknown_type_is_rejected(self):
        self.source_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "USER-DEFINED",
            }
        ]

        self.target_connector.list_columns.return_value = [
            {
                "column_name": "customer_id",
                "data_type": "varchar",
            }
        ]

        with self.assertRaises(SchemaValidationError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
