import tempfile
import unittest
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
