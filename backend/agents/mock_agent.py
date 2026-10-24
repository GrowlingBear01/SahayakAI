import asyncio
from uuid import uuid4

from .base import BrowserAgent, CancelResult, RunResult


class MockBrowserAgent(BrowserAgent):
    def __init__(self) -> None:
        self._cancelled: set[str] = set()

    async def run(self, url: str, goal: str) -> RunResult:
        run_id = str(uuid4())
        await asyncio.sleep(0.05)
        if run_id in self._cancelled:
            return RunResult(False, run_id, error="mock run cancelled")
        if "Submit button exactly once" in goal:
            return RunResult(
                ok=True,
                run_id=run_id,
                final_text="Application received. Reference number: DEMO-MOCK-001",
            )
        return RunResult(
            ok=True,
            run_id=run_id,
            reported_fields={
                "full_name": "Savitri Devi",
                "age": "72",
                "state": "Delhi",
                "phone": "9876543210",
            },
        )

    async def cancel(self, run_id: str) -> CancelResult:
        self._cancelled.add(run_id)
        return CancelResult("CANCELLED", "mock run cancelled")
