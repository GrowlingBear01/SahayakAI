import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.planner import PlannerResult
from backend.schemas import ApproveRequest, TaskState
from backend.task_store import TaskStore
from backend.tests.support import DEMO_REQUEST, wait_for_planner
from mock_site.store import MockStore


class DiscoveryPlanner:
    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        return PlannerResult(
            flow_id="myscheme_discovery",
            values={"age": "72", "state": "Delhi"},
            missing=["age"],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


class DiscoveryAgent:
    def __init__(self, result: RunResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    async def run(self, url: str, goal: str) -> RunResult:
        self.calls.append((url, goal))
        return self.result

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class M9DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def make_orchestrator(self, agent: DiscoveryAgent) -> Orchestrator:
        return Orchestrator(
            TaskStore(),
            agent=agent,
            submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
            planner=DiscoveryPlanner(),
        )

    @staticmethod
    def result_json() -> str:
        return json.dumps(
            {
                "schemes": [
                    {
                        "name": "National Example Scheme",
                        "description": "Support is available to eligible applicants.",
                        "description_hi": "पात्र आवेदकों को सहायता उपलब्ध है।",
                        "scheme_page_url": "https://www.myscheme.gov.in/schemes/example",
                    },
                    {
                        "name": "Unsafe Link Example",
                        "description": "This text is shown on the page.",
                        "description_hi": "यह पाठ पेज पर दिखाया गया है।",
                        "scheme_page_url": "https://evil.example/apply",
                    },
                ],
                "problems": [],
            }
        )

    def test_discovery_requires_approval_and_is_read_only(self) -> None:
        async def scenario() -> None:
            agent = DiscoveryAgent(
                RunResult(True, "discovery-run", final_text=self.result_json())
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.flow_id, "myscheme_discovery")
            self.assertEqual(task.values, {})
            self.assertEqual(agent.calls, [])
            approval = orchestrator._history[task.task_id][-1].data
            self.assertEqual(approval["site_kind"], "real")
            self.assertEqual(approval["fields"], [])
            self.assertIn("read public pages", approval["data_notice_en"])

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )
            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(len(agent.calls), 1)
            url, goal = agent.calls[0]
            self.assertEqual(url, "https://www.myscheme.gov.in/")
            self.assertIn("read-only", goal)
            self.assertIn("Do not enter personal details, apply, submit", goal)
            self.assertNotIn("72", goal)
            self.assertEqual(len(task.schemes), 2)
            self.assertIsNone(task.schemes[1].scheme_page_url)
            self.assertEqual(task.evidence["kind"], "extracted_text")
            final_event = orchestrator._history[task.task_id][-1]
            self.assertEqual(final_event.data["flow_id"], "myscheme_discovery")
            self.assertEqual(final_event.data["schemes"][0]["name"], "National Example Scheme")
            self.assertFalse(final_event.data["offer_demo"])

        asyncio.run(scenario())

    def test_unusable_discovery_results_offer_demo_fallback(self) -> None:
        async def scenario() -> None:
            agent = DiscoveryAgent(
                RunResult(False, "failed-run", error="myScheme request failed")
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find schemes", "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.OUTCOME_UNKNOWN)
            self.assertEqual(task.reason, "discovery_unavailable")
            final_event = orchestrator._history[task.task_id][-1]
            self.assertTrue(final_event.data["offer_demo"])
            self.assertEqual(final_event.data["flow_id"], "myscheme_discovery")

        asyncio.run(scenario())

    def test_unparseable_result_is_not_reported_as_done(self) -> None:
        async def scenario() -> None:
            agent = DiscoveryAgent(
                RunResult(True, "malformed-run", final_text='{"schemes": []')
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find schemes", "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.OUTCOME_UNKNOWN)
            self.assertNotEqual(task.state, TaskState.DONE)
            self.assertTrue(orchestrator._history[task.task_id][-1].data["offer_demo"])

        asyncio.run(scenario())

    def test_accepts_original_m0_shape_and_nested_result_wrappers(self) -> None:
        payload = {
            "schemes": [
                {
                    "name": "Example Scheme",
                    "description": "Description visible on the page.",
                    "scheme_page_url": "https://www.myscheme.gov.in/schemes/example",
                }
            ],
            "problems": [],
        }
        wrapped = json.dumps({"result": json.dumps(payload)})

        parsed = Orchestrator._parse_discovery_output(wrapped)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.schemes[0].name, "Example Scheme")
        self.assertIsNone(parsed.schemes[0].description_hi)

    def test_accepts_fenced_json_without_treating_it_as_successful_empty_results(self) -> None:
        payload = {
            "schemes": [
                {
                    "name": "Example Scheme",
                    "description": "Description visible on the page.",
                }
            ],
            "problems": [],
        }
        fenced = f"```json\n{json.dumps(payload)}\n```"

        parsed = Orchestrator._parse_discovery_output(fenced)

        self.assertIsNotNone(parsed)
        self.assertEqual(len(parsed.schemes), 1)

    def test_login_requirement_hands_off_without_retrying_or_bypassing(self) -> None:
        async def scenario() -> None:
            agent = DiscoveryAgent(
                RunResult(
                    False,
                    "login-run",
                    error="Login required",
                    needs_human="login",
                )
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find schemes", "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "needs_human")
            self.assertEqual(task.needs_human_kind, "login")
            self.assertEqual(len(agent.calls), 1)
            self.assertTrue(orchestrator._history[task.task_id][-1].data["offer_demo"])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
