from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RunResult:
    ok: bool
    run_id: str
    reported_fields: dict[str, str] | None = None
    final_text: str | None = None
    screenshot_url: str | None = None
    streaming_url: str | None = None
    error: str | None = None
    needs_human: str | None = None


@dataclass(frozen=True)
class CancelResult:
    status: str
    message: str | None = None


class BrowserAgent(Protocol):
    async def run(self, url: str, goal: str) -> RunResult: ...

    async def cancel(self, run_id: str) -> CancelResult: ...
