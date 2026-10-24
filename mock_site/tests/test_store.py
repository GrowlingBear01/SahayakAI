import tempfile
import unittest
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from mock_site.store import MockStore


class MockStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        descriptor, database_path = tempfile.mkstemp(suffix=".db")
        os.close(descriptor)
        self.database_path = Path(database_path)
        self.store = MockStore(self.database_path)
        self.payload = {
            "full_name": "Savitri Devi",
            "age": 72,
            "state": "Delhi",
            "phone": "9876543210",
        }

    def tearDown(self) -> None:
        self.database_path.unlink(missing_ok=True)

    def test_rejects_missing_code(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        result = self.store.submit(token, "", self.payload)
        self.assertEqual(result.reason, "invalid_approval_code")

    def test_rejects_wrong_code(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        result = self.store.submit(token, "WRONGCODE", self.payload)
        self.assertEqual(result.reason, "invalid_approval_code")

    def test_token_can_only_be_used_once(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        self.assertTrue(self.store.submit(token, token, self.payload).ok)
        self.assertEqual(
            self.store.submit(token, token, self.payload).reason, "token_already_used"
        )

    def test_rejects_edited_payload(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        edited = {**self.payload, "age": 73}
        self.assertEqual(
            self.store.submit(token, token, edited).reason, "payload_mismatch"
        )

    def test_expired_token_is_rejected(self) -> None:
        with patch("mock_site.store.time.time", return_value=100):
            token = self.store.issue_token("task-1", self.payload, ttl_seconds=1)
        with patch("mock_site.store.time.time", return_value=102):
            result = self.store.submit(token, token, self.payload)
        self.assertEqual(result.reason, "token_expired")

    def test_revoked_token_is_rejected(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        self.assertEqual(self.store.revoke_task_tokens("task-1", "user_stopped"), 1)
        self.assertEqual(
            self.store.submit(token, token, self.payload).reason, "token_revoked"
        )

    def test_verification_requires_matching_task_and_payload(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        self.assertTrue(self.store.submit(token, token, self.payload).ok)

        verified = self.store.verify_submission("task-1", token, self.payload)
        self.assertIsNotNone(verified)
        self.assertTrue(verified.reference_number.startswith("DEMO-"))
        self.assertIsNone(self.store.verify_submission("task-2", token, self.payload))
        self.assertIsNone(
            self.store.verify_submission(
                "task-1", token, {**self.payload, "age": 73}
            )
        )

    def test_rejects_non_positive_token_ttl(self) -> None:
        with self.assertRaises(ValueError):
            self.store.issue_token("task-1", self.payload, ttl_seconds=0)

    def test_concurrent_submits_create_one_record(self) -> None:
        token = self.store.issue_token("task-1", self.payload)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    lambda _: self.store.submit(token, token, self.payload), range(2)
                )
            )
        self.assertEqual(sum(result.ok for result in results), 1)
        self.assertEqual(self.store.submission_count(), 1)


if __name__ == "__main__":
    unittest.main()
