import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.orchestrator import Orchestrator
from backend.planner import PlannerResult
from backend.schemas import TaskState
from backend.task_store import TaskStore
from backend.tests.support import wait_for_planner
from mock_site.store import MockStore


def plan_result(
    values: dict[str, str | int],
    missing: list[str],
    *,
    flow_id: str | None = "mock_scheme_application",
    language: str = "en",
) -> PlannerResult:
    return PlannerResult(
        flow_id=flow_id,
        values=values,
        missing=missing,
        language=language,
        clarifying_question_en="Please provide the missing details.",
        clarifying_question_hi="कृपया बाकी जानकारी दें।",
    )


class QueuePlanner:
    def __init__(self, *results: PlannerResult) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str, dict[str, str | int]]] = []

    async def plan(
        self, transcript, language, flows, values, conversation_history=()
    ) -> PlannerResult:
        self.calls.append((transcript, language, dict(values)))
        return self.results.pop(0)


class M6PlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def create_orchestrator(self, planner: QueuePlanner) -> Orchestrator:
        return Orchestrator(
            TaskStore(),
            submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
            planner=planner,
        )

    def test_missing_information_is_asked_then_answer_is_validated(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner(
                plan_result(
                    {"full_name": "सावित्री देवी"},
                    ["age", "state", "phone"],
                    language="hi",
                ),
                plan_result(
                    {
                        "age": "७२",
                        "state": "Delhi",
                        "phone": "९८७६५४३२१०",
                    },
                    [],
                    language="hi",
                ),
            )
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task(
                "सावित्री देवी के आवेदन में मदद चाहिए", "auto"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(task.missing, ["age", "state", "phone"])
            self.assertEqual(task.values, {"full_name": "सावित्री देवी"})
            self.assertEqual(
                task.clarifying_question_hi, "कृपया बाकी जानकारी दें।"
            )
            self.assertIsNone(task.approval_id)

            task = await orchestrator.answer(
                task.task_id, "उम्र ७२, राज्य Delhi, फ़ोन ९८७६५४३२१०"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.values["age"], 72)
            self.assertEqual(task.values["phone"], "9876543210")
            self.assertEqual(task.values["state"], "Delhi")
            self.assertEqual(task.values["full_name"], "सावित्री देवी")
            self.assertEqual(len(planner.calls), 2)
            self.assertEqual(planner.calls[1][2], {"full_name": "सावित्री देवी"})
            self.assertIn("उम्र ७२", planner.calls[1][0])

        asyncio.run(scenario())

    def test_planner_does_not_get_static_demo_values(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner(
                plan_result({}, ["full_name", "age", "state", "phone"])
            )
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task("Help me with an application", "en")
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(task.values, {})
            self.assertEqual(
                set(task.missing), {"full_name", "age", "state", "phone"}
            )
            self.assertIsNone(task.approval_id)

        asyncio.run(scenario())

    def test_demo_form_uses_local_planner_and_extracts_explicit_fields(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner()
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task(
                "Please fill the demo form: full name Savitri Devi, age 72, "
                "state Delhi, phone 9876543210",
                "en",
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(
                task.values,
                {
                    "full_name": "Savitri Devi",
                    "age": 72,
                    "state": "Delhi",
                    "phone": "9876543210",
                },
            )
            self.assertEqual(planner.calls, [])

            task = await orchestrator.create_task(
                "Fill the demo form", "en", requested_flow="demo"
            )
            task = await wait_for_planner(orchestrator, task.task_id)
            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(
                set(task.missing), {"full_name", "age", "state", "phone"}
            )
            self.assertEqual(planner.calls, [])

        asyncio.run(scenario())

    def test_demo_form_accepts_ordered_answer_without_calling_llm(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner()
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task(
                "Fill the demo form", "en", requested_flow="demo"
            )
            task = await wait_for_planner(orchestrator, task.task_id)
            self.assertEqual(task.state, TaskState.NEEDS_INFO)

            task = await orchestrator.answer(
                task.task_id, "Savitri Devi, 72, Delhi, 9876543210"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(
                task.values,
                {
                    "full_name": "Savitri Devi",
                    "age": 72,
                    "state": "Delhi",
                    "phone": "9876543210",
                },
            )
            self.assertEqual(planner.calls, [])

        asyncio.run(scenario())

    def test_invalid_ordered_demo_details_are_not_saved_as_field_values(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner()
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task(
                "Fill the demo form", "en", requested_flow="demo"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            task = await orchestrator.answer(
                task.task_id, "hey, hej, sdfdjhsl. sdfsfd, sfd"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(task.values, {})
            self.assertEqual(
                set(task.missing), {"full_name", "age", "state", "phone"}
            )
            self.assertIn("in this order", task.clarifying_question_en)
            self.assertIn("10 digits", task.clarifying_question_en)
            self.assertIn("Example:", task.clarifying_question_en)
            self.assertEqual(planner.calls, [])

        asyncio.run(scenario())

    def test_invalid_field_values_are_omitted_and_re_requested(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner(
                plan_result(
                    {
                        "full_name": "Savitri Devi",
                        "age": 121,
                        "state": "Delhi",
                        "phone": "123",
                    },
                    [],
                )
            )
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task(
                "Savitri Devi, age 121, Delhi, phone 123", "en"
            )
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(set(task.missing), {"age", "phone"})
            self.assertNotIn("age", task.values)
            self.assertNotIn("phone", task.values)
            self.assertIsNone(task.approval_id)
            self.assertIn("Age", task.clarifying_question_en)
            self.assertIn("Mobile number", task.clarifying_question_en)

        asyncio.run(scenario())

    def test_unsupported_flow_requires_clarification(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner(
                plan_result(
                    {},
                    [],
                    flow_id="unlisted_flow",
                )
            )
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task("Find a grant", "en")
            task = await wait_for_planner(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertIsNone(task.flow_id)
            self.assertIn("can't perform that action", task.clarifying_question_en)
            self.assertIsNone(task.approval_id)

        asyncio.run(scenario())

    def test_answer_is_rejected_when_task_is_not_needs_info(self) -> None:
        async def scenario() -> None:
            planner = QueuePlanner(
                plan_result(
                    {
                        "full_name": "Savitri Devi",
                        "age": 72,
                        "state": "Delhi",
                        "phone": "9876543210",
                    },
                    [],
                )
            )
            orchestrator = self.create_orchestrator(planner)
            task = await orchestrator.create_task("What can you do?", "en")
            task = await wait_for_planner(orchestrator, task.task_id)

            with self.assertRaisesRegex(ValueError, "not waiting"):
                await orchestrator.answer(task.task_id, "Fill the demo form")

        asyncio.run(scenario())

    def test_numeric_pattern_is_checked_after_digit_normalization(self) -> None:
        orchestrator = self.create_orchestrator(QueuePlanner())
        age_field = next(
            field
            for field in orchestrator.flows["mock_scheme_application"].fields
            if field.key == "age"
        ).model_copy(update={"pattern": r"^7[0-9]$"})

        self.assertEqual(orchestrator._validate_field_value(age_field, "७२"), 72)
        with self.assertRaisesRegex(ValueError, "invalid format"):
            orchestrator._validate_field_value(age_field, "६०")


if __name__ == "__main__":
    unittest.main()
