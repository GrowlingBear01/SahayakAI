import unittest
import time
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.orchestrator import Orchestrator
from backend.planner import GeminiPlanner, PlannerResult
from backend.schemas import Task, TaskState
from backend.task_store import TaskStore
from backend.tests.support import CompleteDemoPlanner, DEMO_REQUEST


class AnswerLoopPlanner:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        self.calls += 1
        if self.calls == 1:
            return PlannerResult(
                flow_id="mock_scheme_application",
                values={"full_name": "Savitri Devi"},
                missing=["age", "state", "phone"],
                language="en",
                clarifying_question_en="Please provide age, state, and phone.",
                clarifying_question_hi="कृपया उम्र, राज्य और फ़ोन बताएं।",
            )
        return PlannerResult(
            flow_id="mock_scheme_application",
            values={
                "age": 72,
                "state": "Delhi",
                "phone": "9876543210",
            },
            missing=[],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.orchestrator = Orchestrator(
            TaskStore(), planner=CompleteDemoPlanner()
        )
        self.orchestrator_patch = patch(
            "backend.main.orchestrator", self.orchestrator
        )
        self.orchestrator_patch.start()
        self.addCleanup(self.orchestrator_patch.stop)
        self.client = TestClient(app)

    def wait_for_planner(self, task_id: str) -> dict:
        for _ in range(200):
            response = self.client.get(f"/tasks/{task_id}")
            self.assertEqual(response.status_code, 200)
            task = response.json()
            if task["state"] != TaskState.PLANNING.value:
                return task
            time.sleep(0.01)
        self.fail("planner did not finish within two seconds")

    def test_health_and_flows(self) -> None:
        self.assertEqual(self.client.get("/health").json(), {"ok": True})
        flows = self.client.get("/flows")
        self.assertEqual(flows.status_code, 200)
        self.assertEqual(flows.json()[0]["id"], "mock_scheme_application")


    def test_task_reaches_done_through_two_approvals(self) -> None:
        task_id = self.client.post(
            "/tasks", json={"text": DEMO_REQUEST, "lang": "en"}
        ).json()["task_id"]
        task = self.wait_for_planner(task_id)
        self.assertEqual(task["state"], "waiting_for_approval")

        response = self.client.post(
            f"/tasks/{task_id}/approve",
            json={"approval_id": task["approval_id"], "edits": None},
        )
        self.assertEqual(response.status_code, 200)
        task = self.wait_for_planner(task_id)
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
        task = self.wait_for_planner(task_id)
        stale = self.client.post(
            f"/tasks/{task_id}/approve",
            json={"approval_id": "stale", "edits": None},
        )
        self.assertEqual(stale.status_code, 409)

        stopped = self.client.post(f"/tasks/{task_id}/stop")
        self.assertEqual(stopped.json()["state"], "stopped")

    def test_answer_endpoint_replans_and_returns_to_approval(self) -> None:
        orchestrator = Orchestrator(
            TaskStore(), planner=AnswerLoopPlanner()
        )
        with patch("backend.main.orchestrator", orchestrator):
            created = self.client.post(
                "/tasks",
                json={"text": "Fill the demo form for Savitri Devi", "lang": "en"},
            )
            task_id = created.json()["task_id"]
            task = self.wait_for_planner(task_id)
            self.assertEqual(task["state"], TaskState.NEEDS_INFO.value)

            answered = self.client.post(
                f"/tasks/{task_id}/answer",
                json={"text": "Age 72, Delhi, phone 9876543210"},
            )
            self.assertEqual(answered.status_code, 200)
            task = self.wait_for_planner(task_id)

        self.assertEqual(task["state"], TaskState.WAITING_FOR_APPROVAL.value)
        self.assertEqual(task["values"]["age"], 72)

    def test_missing_gemini_key_is_reported_as_task_failure(self) -> None:
        orchestrator = Orchestrator(
            TaskStore(),
            planner=GeminiPlanner("", "gemini-3.8-flash", provider="gemini"),
        )
        with patch("backend.main.orchestrator", orchestrator):
            created = self.client.post(
                "/tasks",
                json={"text": "Fill the demo form", "lang": "en"},
            )
            task = self.wait_for_planner(created.json()["task_id"])

        self.assertEqual(task["state"], TaskState.COULD_NOT_FINISH.value)
        self.assertIn("LLM_API_KEY", task["error"])

    def test_approval_card_marks_reported_field_mismatch(self) -> None:
        orchestrator = Orchestrator(TaskStore())
        task = Task(task_id=str(uuid4()), flow_id="mock_scheme_application")
        task.values = {
            "full_name": "Savitri Devi",
            "age": 72,
            "state": "Delhi",
            "phone": "9876543210",
        }
        task.reported_fields = {**{key: str(value) for key, value in task.values.items()}, "age": "73"}
        fields = orchestrator._approval_data(task, "submit")["fields"]
        age = next(field for field in fields if field["label_en"] == "Age")
        self.assertTrue(age["mismatch"])
        self.assertEqual(age["value"], "73")
