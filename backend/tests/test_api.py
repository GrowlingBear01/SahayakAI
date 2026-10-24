import unittest

from fastapi.testclient import TestClient

from backend.main import app


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_and_flows(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"ok": True})
        flows = self.client.get("/flows")
        self.assertEqual(flows.status_code, 200)
        self.assertEqual(flows.json()[0]["id"], "mock_scheme_application")


    def test_task_reaches_done_through_two_approvals(self) -> None:
        task_id = self.client.post(
            "/tasks", json={"text": "Fill the demo form", "lang": "en"}
        ).json()["task_id"]
        task = self.client.get(f"/tasks/{task_id}").json()
        self.assertEqual(task["state"], "waiting_for_approval")

        response = self.client.post(
            f"/tasks/{task_id}/approve",
            json={"approval_id": task["approval_id"], "edits": None},
        )
        self.assertEqual(response.status_code, 200)
        task = self.client.get(f"/tasks/{task_id}").json()
        self.assertEqual(task["approval_type"], "submit")

        response = self.client.post(
            f"/tasks/{task_id}/approve",
            json={"approval_id": task["approval_id"], "edits": None},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(f"/tasks/{task_id}").json()["state"], "done")

        events = self.client.get(f"/tasks/{task_id}/events")
        self.assertIn("waiting_for_approval", events.text)
        self.assertIn("done", events.text)


    def test_stale_approval_is_rejected_and_stop_is_terminal(self) -> None:
        task_id = self.client.post(
            "/tasks", json={"text": "Stop the task", "lang": "en"}
        ).json()["task_id"]
        task = self.client.get(f"/tasks/{task_id}").json()
        stale = self.client.post(
            f"/tasks/{task_id}/approve",
            json={"approval_id": "stale", "edits": None},
        )
        self.assertEqual(stale.status_code, 409)

        stopped = self.client.post(f"/tasks/{task_id}/stop")
        self.assertEqual(stopped.json()["state"], "stopped")
