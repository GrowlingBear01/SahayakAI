import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

RUN_COUNT = 20
MIN_ESTIMATED_BUDGET_USD = 10.0
REPORT_PATH = Path("reports") / "m10_metrics.json"
DEMO_REQUEST = (
    "Fill the demo form for Savitri Devi, age 72, in Delhi, "
    "phone 9876543210."
)
DEMO_VALUES = {
    "full_name": "Savitri Devi",
    "age": 72,
    "state": "Delhi",
    "phone": "9876543210",
}


class M10Planner:
    async def plan(self, transcript, language, flows, values):
        from backend.planner import PlannerResult

        return PlannerResult(
            flow_id="mock_scheme_application",
            values=DEMO_VALUES,
            missing=[],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


class CountingTinyFishAgent:
    def __init__(self, agent) -> None:
        self.agent = agent
        self.run_count = 0

    async def run(self, url: str, goal: str):
        self.run_count += 1
        return await self.agent.run(url, goal)

    async def run_with_callback(
        self,
        url: str,
        goal: str,
        on_run_started,
        on_progress=None,
    ):
        self.run_count += 1
        return await self.agent.run_with_callback(
            url, goal, on_run_started, on_progress
        )

    async def cancel(self, run_id: str):
        return await self.agent.cancel(run_id)


def load_local_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.lstrip("\ufeff").strip(), value)


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [run["latency_seconds"] for run in runs]
    passed = sum(run["passed"] for run in runs)
    return {
        "target_runs": RUN_COUNT,
        "completed_runs": len(runs),
        "passes": passed,
        "failures": len(runs) - passed,
        "pass_rate": passed / len(runs) if runs else 0,
        "median_latency_seconds": (
            round(statistics.median(latencies), 3) if latencies else None
        ),
    }


def write_report(
    runs: list[dict[str, Any]],
    started_at: str,
    wallet_before: float,
    wallet_after: float | None = None,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "milestone": "M10",
        "scope": "20 sequential TinyFish full demo-form runs with fake data",
        "started_at": started_at,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "wallet_before_usd": wallet_before,
        "wallet_after_usd": wallet_after,
        "estimated_wallet_spend_usd": (
            round(wallet_before - wallet_after, 3)
            if wallet_after is not None
            else None
        ),
        "runs": runs,
        "summary": summarize_runs(runs),
        "backup_video": "not_recorded",
    }
    temporary_path = REPORT_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(REPORT_PATH)


async def preflight(
    client: httpx.AsyncClient, base_url: str, api_key: str
) -> tuple[bool, float | None]:
    wallet_response = await client.get(
        f"{base_url}/v1/wallet", headers={"X-API-Key": api_key}
    )
    print(f"wallet_check_http_status={wallet_response.status_code}")
    if wallet_response.status_code not in {200, 404}:
        print("Preflight failed: TinyFish wallet check was rejected.")
        return False, None
    if wallet_response.status_code == 404:
        print("Wallet balance endpoint is unavailable; cannot establish run budget.")
        return False, None

    wallet = wallet_response.json()
    balance_value = (
        wallet.get("available_balance", wallet.get("balance", wallet.get("credits")))
        if isinstance(wallet, dict)
        else None
    )
    try:
        balance = float(balance_value)
    except (TypeError, ValueError):
        balance = None
    if balance is not None:
        currency = wallet.get("currency", "unknown")
        print(f"wallet_balance={balance:.3f} {currency}")
        if currency != "USD" or balance < MIN_ESTIMATED_BUDGET_USD:
            print(
                "Preflight failed: M10 needs at least an estimated "
                f"${MIN_ESTIMATED_BUDGET_USD:.2f} USD budget."
            )
            return False, None
    else:
        print("Preflight failed: wallet balance could not be read.")
        return False, None

    site_url = os.environ.get("MOCK_SITE_BASE_URL", "").rstrip("/")
    parsed_site = urlsplit(site_url)
    if parsed_site.scheme != "https" or not parsed_site.netloc:
        print("Preflight failed: MOCK_SITE_BASE_URL must be a public HTTPS URL.")
        return False, balance
    site_response = await client.get(f"{site_url}/mock/form")
    print(f"demo_form_check_http_status={site_response.status_code}")
    if site_response.status_code != 200:
        print("Preflight failed: the public demo form is not reachable.")
        return False, balance
    if "demo" not in site_response.text.lower():
        print("Preflight failed: the reachable page is not clearly labelled as a demo.")
        return False, balance
    return True, balance


async def read_wallet_balance(
    client: httpx.AsyncClient, base_url: str, api_key: str
) -> float | None:
    response = await client.get(
        f"{base_url}/v1/wallet", headers={"X-API-Key": api_key}
    )
    if response.is_error:
        print(f"wallet_after_http_status={response.status_code}")
        return None
    wallet = response.json()
    if not isinstance(wallet, dict) or wallet.get("currency") != "USD":
        return None
    try:
        return float(wallet.get("available_balance", wallet.get("balance")))
    except (TypeError, ValueError):
        return None


async def run_cycle(orchestrator) -> tuple[bool, str]:
    from backend.schemas import ApproveRequest, TaskState

    task = await orchestrator.create_task(DEMO_REQUEST, "en")
    for _ in range(2000):
        task = orchestrator.store.get(task.task_id)
        if task is None:
            raise RuntimeError("M10 task disappeared before approval")
        if task.state != TaskState.PLANNING:
            break
        await asyncio.sleep(0.001)

    if task.state != TaskState.WAITING_FOR_APPROVAL:
        return False, f"planner_state:{task.state.value}"

    task = await orchestrator.approve(
        task.task_id, ApproveRequest(approval_id=task.approval_id)
    )
    if task.state != TaskState.WAITING_FOR_APPROVAL or task.approval_type != "submit":
        return False, f"fill_state:{task.state.value}"

    task = await orchestrator.approve(
        task.task_id, ApproveRequest(approval_id=task.approval_id)
    )
    return task.state == TaskState.DONE, task.state.value


async def main() -> int:
    load_local_env()
    api_key = os.environ.get("TINYFISH_API_KEY", "")
    if not api_key:
        print("M10 aborted: TINYFISH_API_KEY is not configured.")
        return 2

    base_url = os.environ.get(
        "TINYFISH_BASE_URL", "https://agent.tinyfish.ai"
    ).rstrip("/")
    started_at = datetime.now(timezone.utc).isoformat()
    runs: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        preflight_ok, wallet_before = await preflight(client, base_url, api_key)
        if not preflight_ok or wallet_before is None:
            return 2

        from backend.agents.tinyfish_agent import TinyFishAgent
        from backend.orchestrator import Orchestrator
        from backend.task_store import TaskStore
        from mock_site.store import MockStore, database_path

        agent = CountingTinyFishAgent(
            TinyFishAgent(api_key, base_url=base_url, client=client)
        )
        orchestrator = Orchestrator(
            TaskStore(),
            agent=agent,
            submission_store=MockStore(database_path()),
            planner=M10Planner(),
        )

        print(
            "Starting 20 sequential TinyFish demo cycles. Each cycle uses the "
            "fake values in this script and has separate start and submit approvals."
        )
        for cycle_number in range(1, RUN_COUNT + 1):
            started = time.monotonic()
            calls_before = agent.run_count
            try:
                passed, outcome = await run_cycle(orchestrator)
            except Exception as error:
                passed = False
                outcome = f"runner_error:{type(error).__name__}"
                write_report(runs, started_at, wallet_before)
                print(
                    f"Cycle {cycle_number} aborted on runner error "
                    f"({type(error).__name__}); partial metrics saved."
                )
                raise

            run_record = {
                "cycle": cycle_number,
                "passed": passed,
                "outcome": outcome,
                "latency_seconds": round(time.monotonic() - started, 3),
                "tinyfish_runs": agent.run_count - calls_before,
            }
            runs.append(run_record)
            write_report(runs, started_at, wallet_before)
            print(
                f"cycle={cycle_number}/{RUN_COUNT} passed={passed} "
                f"outcome={outcome} latency_seconds={run_record['latency_seconds']} "
                f"tinyfish_runs={run_record['tinyfish_runs']}"
            )

        summary = summarize_runs(runs)
        wallet_after = await read_wallet_balance(client, base_url, api_key)
        write_report(runs, started_at, wallet_before, wallet_after)
        print(json.dumps(summary, indent=2))
        print(f"metrics_file={REPORT_PATH}")
        if wallet_after is not None:
            print(f"wallet_after_usd={wallet_after:.3f}")
            print(f"estimated_wallet_spend_usd={wallet_before - wallet_after:.3f}")
        print("backup_video=not_recorded")
        return 0 if summary["failures"] == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
