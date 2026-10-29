import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from app.services.governance_lifecycle_service import GovernanceLifecycleService


class GovernanceLifecycleServiceTests(unittest.TestCase):
    def test_production_never_allows_automatic_governance(self):
        connection = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = (True, "PROD", 1)
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        service = GovernanceLifecycleService(connection_factory=lambda: connection)

        with self.assertRaisesRegex(PermissionError, "production"):
            service.activate_and_publish(
                tenant_id=1, project_id=1, environment_id=8,
                mapping_version_id=1, pipeline_version_id=1,
                auto_governance=True,
            )
        connection.rollback.assert_called_once()

    def test_existing_active_published_versions_are_reused(self):
        connection = Mock()
        cursor = Mock()
        cursor.fetchone.side_effect = [(False, "DEV", 1), ("ACTIVE",), ("PUBLISHED",)]
        connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
        connection.cursor.return_value.__exit__ = Mock(return_value=False)
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        service = GovernanceLifecycleService(connection_factory=lambda: connection)

        result = service.activate_and_publish(
            tenant_id=1, project_id=1, environment_id=1,
            mapping_version_id=1, pipeline_version_id=1,
            auto_governance=True,
        )

        self.assertEqual(result.mapping_status, "ACTIVE")
        self.assertEqual(result.pipeline_status, "PUBLISHED")
        connection.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
