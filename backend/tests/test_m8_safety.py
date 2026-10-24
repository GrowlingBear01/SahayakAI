import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.schemas import ApproveRequest, TaskState
from backend.task_store import TaskStore
from backend.planner import PlannerResult
from backend.tests.support import CompleteDemoPlanner, DEMO_REQUEST, wait_for_planner
from mock_site.store import MockStore


class RetryThenSuccessAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, url: str, goal: str) -> RunResult:
        self.calls += 1
        if self.calls < 3:
            return RunResult(False, f"run-{self.calls}", error="connection timed out")
        return RunResult(
            True,
            "run-success",
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class HumanRequiredAgent:
    async def run(self, url: str, goal: str) -> RunResult:
        return RunResult(
            False,
            "human-required",
            error="The website requires human action",
            needs_human="captcha",
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class BlockingAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled: list[str] = []

    async def run(self, url: str, goal: str) -> RunResult:
        return await self.run_with_callback(url, goal, None)

    async def run_with_callback(self, url, goal, on_run_started, on_progress=None):
        run_id = "blocked-run"
        if on_run_started:
            on_run_started(run_id)
        if on_progress:
            await on_progress("https://stream.example/blocked-run", "Opening the form")
        self.started.set()
        await self.release.wait()
        return RunResult(
            True,
            run_id,
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
        )

    async def cancel(self, run_id: str) -> CancelResult:
        self.cancelled.append(run_id)
        return CancelResult("CANCELLED")


class UnconfirmedCancellationAgent(BlockingAgent):
    async def cancel(self, run_id: str) -> CancelResult:
        self.cancelled.append(run_id)
        return CancelResult("UNKNOWN")


class WaitingPlanner:
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        self.started.set()
        await asyncio.Event().wait()


class MissingInfoPlanner:
    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        return PlannerResult(
            flow_id=None,
            values={},
            missing=[],
            language="en",
            clarifying_question_en="Which task do you need?",
            clarifying_question_hi="आपको कौन सा काम चाहिए?",
        )


class FailingAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, url: str, goal: str) -> RunResult:
        self.calls += 1
        return RunResult(False, f"run-{self.calls}", error="connection timed out")

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class SubmissionFailAgent:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, url: str, goal: str) -> RunResult:
        self.calls += 1
        if "click the Submit button exactly once" in goal:
            return RunResult(False, "submit-run", error="connection timed out")
        return RunResult(
            True,
            "fill-run",
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class DelayedSubmitAgent:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, url: str, goal: str) -> RunResult:
        if "click the Submit button exactly once" in goal:
            self.started.set()
            await self.release.wait()
            return RunResult(False, "submit-run", error="connection timed out")
        return RunResult(
            True,
            "fill-run",
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class RecordedDelayedSubmitAgent:
    def __init__(self, submission_store: MockStore) -> None:
        self.submission_store = submission_store
        self.orchestrator: Orchestrator | None = None
        self.recorded = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, url: str, goal: str) -> RunResult:
        if "click the Submit button exactly once" not in goal:
            return RunResult(
                True,
                "fill-run",
                reported_fields={
                    "full_name": "Savitri Devi",
                    "age": "72",
                    "state": "Delhi",
                    "phone": "9876543210",
                },
            )

        assert self.orchestrator is not None
        task_id, token = next(iter(self.orchestrator._submission_tokens.items()))
        submission = self.submission_store.submit(
            token,
            token,
            {
                "full_name": "Savitri Devi",
                "age": 72,
                "state": "Delhi",
                "phone": "9876543210",
            },
        )
        self.recorded.set()
        await self.release.wait()
        return RunResult(
            submission.ok,
            "submit-run",
            final_text=submission.reference_number,
            error=submission.reason,
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class FailingVerifyStore(MockStore):
    def verify_submission(self, task_id, token, payload):
        raise sqlite3.OperationalError("database unavailable")


class M8SafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "mock.db"

    def make_orchestrator(self, agent=None, planner=None) -> Orchestrator:
        return Orchestrator(
            TaskStore(),
            agent=agent,
            submission_store=MockStore(self.database_path),
            planner=planner or CompleteDemoPlanner(),
        )

    def test_stop_cancels_active_browser_run_and_ignores_late_result(self) -> None:
        async def scenario() -> None:
            agent = BlockingAgent()
            orchestrator = self.make_orchestrator(agent=agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            pending_approval = asyncio.create_task(
                orchestrator.approve(
                    task.task_id,
                    request=ApproveRequest(approval_id=task.approval_id),
                )
            )
            await agent.started.wait()
            progress_events = [
                event
                for event in orchestrator._history[task.task_id]
                if event.data.get("streaming_url")
                == "https://stream.example/blocked-run"
            ]
            self.assertEqual(len(progress_events), 1)
            self.assertEqual(progress_events[0].state, TaskState.WORKING)
            self.assertEqual(progress_events[0].data["action"], "Opening the form")

            stopped = await orchestrator.stop(task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)
            self.assertEqual(agent.cancelled, ["blocked-run"])

            agent.release.set()
            await pending_approval
            final = orchestrator.store.get(task.task_id)
            self.assertEqual(final.state, TaskState.STOPPED)
            self.assertIsNone(final.approval_id)

        asyncio.run(scenario())

    def test_stop_reports_unconfirmed_browser_cancellation(self) -> None:
        async def scenario() -> None:
            agent = UnconfirmedCancellationAgent()
            orchestrator = self.make_orchestrator(agent=agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            pending = asyncio.create_task(
                orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=task.approval_id),
                )
            )
            await agent.started.wait()

            stopped = await orchestrator.stop(task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)
            self.assertIn("did not confirm cancellation", stopped.error)
            self.assertEqual(agent.cancelled, ["blocked-run"])

            agent.release.set()
            await pending
            self.assertEqual(
                orchestrator.store.get(task.task_id).state,
                TaskState.STOPPED,
            )

        asyncio.run(scenario())

    def test_stop_works_during_planning_needs_info_and_approval_wait(self) -> None:
        async def scenario() -> None:
            planner = WaitingPlanner()
            orchestrator = self.make_orchestrator(planner=planner)
            planning_task = await orchestrator.create_task(DEMO_REQUEST, "en")
            await planner.started.wait()
            stopped = await orchestrator.stop(planning_task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)

            needs_info = self.make_orchestrator(planner=MissingInfoPlanner())
            question_task = await needs_info.create_task("help me", "en")
            question_task = await wait_for_planner(needs_info, question_task.task_id)
            self.assertEqual(question_task.state, TaskState.NEEDS_INFO)
            stopped = await needs_info.stop(question_task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)

            waiting_approval = self.make_orchestrator()
            approval_task = await waiting_approval.create_task(DEMO_REQUEST, "en")
            approval_task = await wait_for_planner(
                waiting_approval, approval_task.task_id
            )
            self.assertEqual(approval_task.state, TaskState.WAITING_FOR_APPROVAL)
            stopped = await waiting_approval.stop(approval_task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)

        asyncio.run(scenario())

    def test_working_transient_errors_retry_at_most_twice(self) -> None:
        async def scenario() -> None:
            agent = RetryThenSuccessAgent()
            orchestrator = self.make_orchestrator(agent=agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(agent.calls, 3)
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.approval_type, "submit")
            retry_events = [
                event
                for event in orchestrator._history[task.task_id]
                if event.data.get("action") == "Retrying browser run"
            ]
            self.assertEqual(len(retry_events), 2)

        asyncio.run(scenario())

    def test_working_retry_exhaustion_stops_after_two_retries(self) -> None:
        async def scenario() -> None:
            agent = FailingAgent()
            orchestrator = self.make_orchestrator(agent=agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(agent.calls, 3)
            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(
                sum(
                    event.data.get("action") == "Retrying browser run"
                    for event in orchestrator._history[task.task_id]
                ),
                2,
            )

        asyncio.run(scenario())

    def test_submission_failure_is_never_retried(self) -> None:
        async def scenario() -> None:
            agent = SubmissionFailAgent()
            orchestrator = self.make_orchestrator(agent=agent)
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(agent.calls, 2)
            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "not_submitted")

        asyncio.run(scenario())

    def test_stop_with_database_failure_reports_unknown(self) -> None:
        async def scenario() -> None:
            agent = DelayedSubmitAgent()
            store = FailingVerifyStore(self.database_path)
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )
            pending = asyncio.create_task(
                orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=task.approval_id),
                )
            )
            await agent.started.wait()

            stopped = await orchestrator.stop(task.task_id)
            self.assertEqual(stopped.state, TaskState.OUTCOME_UNKNOWN)
            self.assertEqual(stopped.reason, "db_unavailable")

            agent.release.set()
            await pending
            self.assertEqual(
                orchestrator.store.get(task.task_id).state,
                TaskState.OUTCOME_UNKNOWN,
            )

        asyncio.run(scenario())

    def test_stop_after_authoritative_record_reports_verified_completion(self) -> None:
        async def scenario() -> None:
            submission_store = MockStore(self.database_path)
            agent = RecordedDelayedSubmitAgent(submission_store)
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            agent.orchestrator = orchestrator
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )
            pending = asyncio.create_task(
                orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=task.approval_id),
                )
            )
            await agent.recorded.wait()

            stopped = await orchestrator.stop(task.task_id)
            self.assertEqual(stopped.state, TaskState.DONE)
            self.assertEqual(
                orchestrator._history[task.task_id][-1].data["note"],
                "stop_too_late",
            )

            agent.release.set()
            await pending
            final = orchestrator.store.get(task.task_id)
            self.assertEqual(final.state, TaskState.DONE)
            self.assertEqual(final.evidence["kind"], "verified_confirmation")

        asyncio.run(scenario())

    def test_human_action_returns_could_not_finish_with_kind(self) -> None:
        async def scenario() -> None:
            orchestrator = self.make_orchestrator(agent=HumanRequiredAgent())
            orchestrator.flows["mock_scheme_application"] = (
                orchestrator.flows["mock_scheme_application"].model_copy(
                    update={"url": "https://demo.example/mock/form"}
                )
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "needs_human")
            self.assertEqual(task.needs_human_kind, "captcha")
            self.assertEqual(
                task.human_action_url, "https://demo.example/mock/form"
            )
            event = orchestrator._history[task.task_id][-1]
            self.assertEqual(event.data["reason"], "needs_human")
            self.assertEqual(event.data["needs_human_kind"], "captcha")
            self.assertEqual(
                event.data["human_action_url"],
                "https://demo.example/mock/form",
            )
            snapshot = orchestrator._snapshot_event(task)
            self.assertEqual(snapshot.data["reason"], "needs_human")
            self.assertEqual(snapshot.data["needs_human_kind"], "captcha")
            self.assertEqual(
                snapshot.data["human_action_url"],
                "https://demo.example/mock/form",
            )

        asyncio.run(scenario())
