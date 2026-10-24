import asyncio
import tempfile
import unittest
from pathlib import Path

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.schemas import ApproveRequest, TaskState
from backend.task_store import TaskStore
from backend.tests.support import (
    CompleteDemoPlanner,
    DEMO_REQUEST,
    wait_for_planner,
)
from mock_site.store import MockStore


class RecordingMockStore(MockStore):
    def __init__(self, database_path: Path) -> None:
        self.issued_tokens: list[str] = []
        super().__init__(database_path)

    def issue_token(self, task_id, payload, ttl_seconds=180):
        token = super().issue_token(task_id, payload, ttl_seconds)
        self.issued_tokens.append(token)
        return token


class UnverifiedAgent:
    def __init__(self) -> None:
        self.submit_calls = 0

    async def run(self, url: str, goal: str) -> RunResult:
        if "click the Submit button exactly once" in goal:
            self.submit_calls += 1
            return RunResult(
                True,
                "unverified-run",
                final_text="Application received. Reference number: FAKE-123",
            )
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


class LostResponseAgent:
    def __init__(self, submission_store: RecordingMockStore) -> None:
        self.submission_store = submission_store

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
        token = self.submission_store.issued_tokens[-1]
        self.submission_store.submit(
            token,
            token,
            {
                "full_name": "Savitri Devi",
                "age": 72,
                "state": "Delhi",
                "phone": "9876543210",
            },
        )
        raise RuntimeError("connection closed after server accepted submission")

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("UNKNOWN")


class DelayedSubmitAgent:
    def __init__(self, submission_store: RecordingMockStore) -> None:
        self.submission_store = submission_store
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.submit_calls = 0

    async def run(self, url: str, goal: str) -> RunResult:
        if "click the Submit button exactly once" in goal:
            self.submit_calls += 1
            self.started.set()
            await self.release.wait()
            token = self.submission_store.issued_tokens[-1]
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
            return RunResult(
                submission.ok,
                "delayed-submit",
                final_text=submission.reference_number,
                error=submission.reason,
            )
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


class M5VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "mock.db"

    def test_mock_flow_issues_token_only_after_submit_approval_and_verifies(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            orchestrator = Orchestrator(
                TaskStore(),
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            self.assertEqual(submission_store.issued_tokens, [])

            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            self.assertEqual(task.approval_type, "submit")
            self.assertEqual(submission_store.issued_tokens, [])

            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(len(submission_store.issued_tokens), 1)
            verified = submission_store.verify_submission(
                task.task_id,
                submission_store.issued_tokens[0],
                task.values,
            )
            self.assertIsNotNone(verified)
            self.assertEqual(task.evidence["text"].split()[-1], verified.reference_number)

        asyncio.run(scenario())

    def test_unverified_agent_report_is_not_submitted_and_cannot_be_retried(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            agent = UnverifiedAgent()
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            submit_approval_id = task.approval_id
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=submit_approval_id)
            )

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "unverified_claim")
            self.assertIn("no server record", task.error)
            self.assertEqual(agent.submit_calls, 1)
            self.assertEqual(submission_store.submission_count(), 0)
            with self.assertRaises(ValueError):
                await orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=submit_approval_id),
                )
            self.assertEqual(agent.submit_calls, 1)

        asyncio.run(scenario())

    def test_lost_agent_response_uses_authoritative_record(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            agent = LostResponseAgent(submission_store)
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(submission_store.submission_count(), 1)

        asyncio.run(scenario())

    def test_submit_edits_require_a_fresh_fill_and_review(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            orchestrator = Orchestrator(
                TaskStore(),
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )

            with self.assertRaisesRegex(ValueError, "above the maximum"):
                await orchestrator.approve(
                    task.task_id,
                    ApproveRequest(
                        approval_id=task.approval_id,
                        edits={"age": 121},
                    ),
                )
            self.assertEqual(submission_store.issued_tokens, [])

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(
                    approval_id=task.approval_id,
                    edits={"full_name": "Asha Devi"},
                ),
            )
            self.assertEqual(task.approval_type, "start")
            self.assertIsNone(task.reported_fields)

            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            self.assertEqual(task.approval_type, "submit")
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(len(submission_store.issued_tokens), 1)

        asyncio.run(scenario())

    def test_submit_approval_rejects_unmatched_reported_fields(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            orchestrator = Orchestrator(
                TaskStore(),
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            task.reported_fields["age"] = "73"
            orchestrator.store.replace(task)

            with self.assertRaisesRegex(ValueError, "do not match"):
                await orchestrator.approve(
                    task.task_id, ApproveRequest(approval_id=task.approval_id)
                )
            self.assertEqual(submission_store.issued_tokens, [])

        asyncio.run(scenario())

    def test_stop_revokes_token_before_delayed_submission(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            agent = DelayedSubmitAgent(submission_store)
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )

            pending_submission = asyncio.create_task(
                orchestrator.approve(
                    task.task_id, ApproveRequest(approval_id=task.approval_id)
                )
            )
            await agent.started.wait()
            stopped = await orchestrator.stop(task.task_id)
            self.assertEqual(stopped.state, TaskState.STOPPED)

            agent.release.set()
            final_task = await pending_submission
            self.assertEqual(final_task.state, TaskState.STOPPED)
            self.assertEqual(submission_store.submission_count(), 0)

        asyncio.run(scenario())

    def test_duplicate_submit_approval_only_starts_one_run(self) -> None:
        async def scenario() -> None:
            submission_store = RecordingMockStore(self.database_path)
            agent = DelayedSubmitAgent(submission_store)
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=submission_store,
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id, ApproveRequest(approval_id=task.approval_id)
            )
            submit_approval_id = task.approval_id
            pending_submission = asyncio.create_task(
                orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=submit_approval_id),
                )
            )
            await agent.started.wait()

            with self.assertRaises(ValueError):
                await orchestrator.approve(
                    task.task_id,
                    ApproveRequest(approval_id=submit_approval_id),
                )
            self.assertEqual(len(submission_store.issued_tokens), 1)
            agent.release.set()
            final_task = await pending_submission

            self.assertEqual(final_task.state, TaskState.DONE)
            self.assertEqual(agent.submit_calls, 1)
            self.assertEqual(submission_store.submission_count(), 1)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
