import asyncio
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.schemas import ApproveRequest, TaskState
from backend.task_store import TaskStore
from backend.tests.support import CompleteDemoPlanner, DEMO_REQUEST, wait_for_planner
from mock_site.store import MockStore


class StreamingAgent:
    async def run(self, url: str, goal: str) -> RunResult:
        return RunResult(
            True,
            "tinyfish-run",
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
            screenshot_url="https://screenshots.example/fill.png",
            streaming_url="https://stream.example/run",
        )

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class M4RuntimeTests(unittest.TestCase):
    def test_fill_result_passes_tinyfish_view_to_approval_event(self) -> None:
        async def scenario(database_path: Path) -> None:
            orchestrator = Orchestrator(
                TaskStore(),
                agent=StreamingAgent(),
                submission_store=MockStore(database_path),
                planner=CompleteDemoPlanner(),
            )
            task = await orchestrator.create_task(DEMO_REQUEST, "en")
            task = await wait_for_planner(orchestrator, task.task_id)
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            review_event = orchestrator._history[task.task_id][-1]
            self.assertEqual(
                review_event.data["streaming_url"],
                "https://stream.example/run",
            )
            self.assertEqual(
                review_event.data["screenshot_url"],
                "https://screenshots.example/fill.png",
            )

        with TemporaryDirectory() as temp_dir:
            asyncio.run(scenario(Path(temp_dir) / "mock.db"))


if __name__ == "__main__":
    unittest.main()
