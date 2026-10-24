import importlib
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from mock_site.store import MockStore


site_app = importlib.import_module("mock_site.app")


class MockSiteRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_store = site_app.store
        self.store = MockStore(Path(self.temp_dir.name) / "mock.db")
        site_app.store = self.store
        self.addCleanup(setattr, site_app, "store", self.original_store)
        self.client = TestClient(site_app.app)
        self.payload = {
            "full_name": "Savitri Devi",
            "age": "72",
            "state": "Delhi",
            "phone": "9876543210",
        }

    def test_route_accepts_approved_payload_once_and_returns_reference(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        response = self.client.post(
            "/mock/submit",
            data={**self.payload, "approval_code": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Application received", response.text)
        self.assertIsNotNone(
            self.store.verify_submission("task-1", token, self.payload)
        )

        replay = self.client.post(
            "/mock/submit",
            data={**self.payload, "approval_code": token},
        )
        self.assertEqual(replay.status_code, 400)
        self.assertIn("token_already_used", replay.text)

    def test_route_rejects_modified_approved_payload(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        response = self.client.post(
            "/mock/submit",
            data={**self.payload, "age": "73", "approval_code": token},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("payload_mismatch", response.text)
        self.assertEqual(self.store.submission_count(), 0)


if __name__ == "__main__":
    unittest.main()
