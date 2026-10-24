import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

from .base import BrowserAgent, CancelResult, RunResult
from mock_site.store import MockStore


class MockBrowserAgent(BrowserAgent):
    MOCK_CONTEXT = "SAHAYAKAI_MOCK_CONTEXT="

    def __init__(self, submission_store: MockStore) -> None:
        self.submission_store = submission_store
        self._cancelled: set[str] = set()

    async def run(self, url: str, goal: str) -> RunResult:
        return await self.run_with_callback(url, goal, None)

    async def run_with_callback(
        self,
        url: str,
        goal: str,
        on_run_started: Callable[[str], None] | None,
        on_progress: Callable[[str | None, str | None], Awaitable[None]]
        | None = None,
    ) -> RunResult:
        run_id = str(uuid4())
        if on_run_started is not None:
            on_run_started(run_id)
        if on_progress is not None:
            await on_progress(None, "Running the local mock browser agent.")
        await asyncio.sleep(0.05)
        if run_id in self._cancelled:
            return RunResult(False, run_id, error="mock run cancelled")
        context = self._context(goal)
        if context and context.get("operation") == "submit":
            payload = context.get("payload")
            token = context.get("approval_code")
            task_id = context.get("task_id")
            if not isinstance(payload, dict) or not isinstance(token, str) or not isinstance(task_id, str):
                return RunResult(False, run_id, error="mock submission context is invalid")
            submission = self.submission_store.submit(token, token, payload)
            if not submission.ok:
                return RunResult(
                    False,
                    run_id,
                    error=f"mock submission rejected: {submission.reason}",
                )
            return RunResult(
                ok=True,
                run_id=run_id,
                final_text=(
                    "Application received. Reference number: "
                    f"{submission.reference_number}"
                ),
            )
        if context and context.get("operation") == "fill":
            payload = context.get("payload")
            if not isinstance(payload, dict):
                return RunResult(False, run_id, error="mock fill context is invalid")
            return RunResult(
                ok=True,
                run_id=run_id,
                reported_fields={str(key): str(value) for key, value in payload.items()},
            )
        return RunResult(
            ok=False,
            run_id=run_id,
            error="mock agent did not receive a supported operation",
        )

    async def cancel(self, run_id: str) -> CancelResult:
        self._cancelled.add(run_id)
        return CancelResult("CANCELLED", "mock run cancelled")

    @classmethod
    def _context(cls, goal: str) -> dict | None:
        match = re.search(rf"{re.escape(cls.MOCK_CONTEXT)}(.+)$", goal, re.DOTALL)
        if match is None:
            return None
        try:
            context = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
        return context if isinstance(context, dict) else None
