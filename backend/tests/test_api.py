import unittest
import time
from dataclasses import replace
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app, configure_cors
from backend.orchestrator import Orchestrator
from backend.planner import (
    GeminiPlanner,
    PlannerRateLimitError,
    PlannerResult,
)
from backend.schemas import Task, TaskState
from backend.task_store import TaskStore
from backend.tests.support import CompleteDemoPlanner, DEMO_REQUEST


class AnswerLoopPlanner:
    def __init__(self) -> None:
        self.calls = 0

    async def plan(
        self, transcript, language, flows, values, conversation_history=()
    ) -> PlannerResult:
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
        flow_ids = {flow["id"] for flow in flows.json()}
        self.assertIn("mock_scheme_application", flow_ids)
        self.assertIn("myscheme_discovery", flow_ids)
        self.assertIn("web_discovery", flow_ids)

    def test_readiness_checks_required_provider_configuration(self) -> None:
        with patch(
            "backend.main.settings",
            replace(settings, llm_provider="gemini", llm_api_key="", browser_agent="mock"),
        ):
            not_ready = self.client.get("/ready")
        self.assertEqual(not_ready.status_code, 503)
        self.assertFalse(not_ready.json()["ok"])
        self.assertFalse(not_ready.json()["checks"]["llm_api_key"])

        with patch(
            "backend.main.settings",
            replace(
                settings,
                llm_provider="gemini",
                llm_api_key="test-key",
                browser_agent="mock",
            ),
        ):
            ready = self.client.get("/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json()["ok"])

    def test_cors_allows_only_configured_origins(self) -> None:
        cors_app = FastAPI()
        configure_cors(cors_app, ("https://frontend.example",))

        @cors_app.get("/health")
        async def cors_health():
            return {"ok": True}

        with TestClient(cors_app) as client:
            allowed = client.options(
                "/health",
                headers={
                    "Origin": "https://frontend.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
            denied = client.options(
                "/health",
                headers={
                    "Origin": "https://attacker.example",
                    "Access-Control-Request-Method": "GET",
                },
            )
        self.assertEqual(
            allowed.headers["access-control-allow-origin"],
            "https://frontend.example",
        )
        self.assertNotIn("access-control-allow-origin", denied.headers)
        with self.assertRaisesRegex(ValueError, "exact trusted origins"):
            configure_cors(FastAPI(), ("*",))


    def test_web_flow_selection_is_preserved_for_site_discovery(self) -> None:
        created = self.client.post(
            "/tasks",
            json={
                "text": "National Scholarship Portal",
                "lang": "en",
                "flow": "web",
            },
        )
        self.assertEqual(created.status_code, 200)
        task = self.wait_for_planner(created.json()["task_id"])
        self.assertEqual(task["requested_flow"], "web")
        self.assertEqual(task["flow_id"], "web_discovery")
        self.assertEqual(task["state"], "needs_info")
        self.assertEqual(task["web_phase"], "site_name")


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
        stopped_result = stopped.json()
        self.assertEqual(stopped_result["state"], "stopped")
        self.assertEqual(stopped_result["reason"], None)
        self.assertIn("Stopped", stopped_result["summary_en"])

    def test_answer_endpoint_replans_and_returns_to_approval(self) -> None:
        orchestrator = Orchestrator(
            TaskStore(), planner=AnswerLoopPlanner()
        )
        with patch("backend.main.orchestrator", orchestrator):
            created = self.client.post(
                "/tasks",
                json={"text": "Savitri Devi needs help with an application", "lang": "en"},
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

    def test_demo_form_does_not_require_gemini_planner(self) -> None:
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

        self.assertEqual(task["state"], TaskState.NEEDS_INFO.value)
        self.assertEqual(task["missing"], ["full_name", "age", "state", "phone"])

    def test_gemini_quota_error_is_actionable_and_localized(self) -> None:
        class RateLimitedPlanner:
            async def plan(
                self, transcript, language, flows, values, conversation_history=()
            ):
                raise PlannerRateLimitError("quota reached")

        orchestrator = Orchestrator(TaskStore(), planner=RateLimitedPlanner())
        with patch("backend.main.orchestrator", orchestrator):
            created = self.client.post(
                "/tasks",
                json={
                    "text": "Find schemes listed on myScheme",
                    "lang": "en",
                },
            )
            task = self.wait_for_planner(created.json()["task_id"])

        self.assertEqual(task["state"], TaskState.COULD_NOT_FINISH.value)
        self.assertEqual(task["reason"], "planner_rate_limited")
        self.assertIn("quota has been reached", task["error"])
        self.assertIn("कोटा", task["error_hi"])

    def test_general_conversation_completes_without_choosing_a_form(self) -> None:
        class ConversationPlanner:
            history = None

            async def plan(
                self, transcript, language, flows, values, conversation_history=()
            ):
                self.history = list(conversation_history)
                return PlannerResult(
                    action="conversation",
                    flow_id=None,
                    values={},
                    missing=[],
                    language="en",
                    clarifying_question_en="",
                    clarifying_question_hi="",
                    response_en="Sure—I'll make the note warmer.",
                    response_hi="ज़रूर—मैं संदेश को और आत्मीय बनाऊँगा।",
                )

        planner = ConversationPlanner()
        orchestrator = Orchestrator(TaskStore(), planner=planner)
        history = [
            {"role": "user", "text": "Help me write a thank-you note."},
            {"role": "assistant", "text": "Who is it for?"},
        ]
        with patch("backend.main.orchestrator", orchestrator):
            created = self.client.post(
                "/tasks",
                json={
                    "text": "Make it warmer.",
                    "lang": "en",
                    "history": history,
                },
            )
            task = self.wait_for_planner(created.json()["task_id"])

        self.assertEqual(task["state"], TaskState.DONE.value)
        self.assertEqual(task["reason"], "conversation")
        self.assertEqual(
            task["assistant_response_en"], "Sure—I'll make the note warmer."
        )
        self.assertEqual(
            [turn.model_dump() for turn in planner.history],
            history,
        )
        self.assertNotIn("conversation_history", task)

    def test_task_request_rejects_unbounded_conversation_history(self) -> None:
        response = self.client.post(
            "/tasks",
            json={
                "text": "Hello",
                "history": [
                    {"role": "user", "text": f"turn {index}"}
                    for index in range(13)
                ],
            },
        )
        self.assertEqual(response.status_code, 422)

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
