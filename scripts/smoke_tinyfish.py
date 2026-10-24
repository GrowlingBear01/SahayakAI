import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx


TERMINAL_STATES = {"COMPLETED", "FAILED", "CANCELLED"}


def load_local_env() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.lstrip("\ufeff").strip()
        os.environ.setdefault(key, value)


async def run_agent(client: httpx.AsyncClient, url: str, goal: str) -> dict:
    base_url = os.environ.get("TINYFISH_BASE_URL", "https://agent.tinyfish.ai").rstrip("/")
    headers = {
        "X-API-Key": os.environ["TINYFISH_API_KEY"],
        "Content-Type": "application/json",
    }
    response = await client.post(
        f"{base_url}/v1/automation/run-async",
        headers=headers,
        json={"url": url, "goal": goal},
    )
    response.raise_for_status()
    run_id = response.json()["run_id"]
    started_at = time.monotonic()
    latest: dict = {}
    while time.monotonic() - started_at < 120:
        await asyncio.sleep(2)
        latest = (
            await client.get(f"{base_url}/v1/runs/{run_id}", headers=headers)
        ).json()
        if latest.get("status") in TERMINAL_STATES:
            latest["elapsed_seconds"] = round(time.monotonic() - started_at, 1)
            return latest

    cancel = await client.post(f"{base_url}/v1/runs/{run_id}/cancel", headers=headers)
    return {
        "run_id": run_id,
        "status": "WATCHDOG_CANCEL_REQUESTED",
        "elapsed_seconds": round(time.monotonic() - started_at, 1),
        "cancel": cancel.json(),
        "last_run": latest,
    }


async def main() -> int:
    load_local_env()
    required = ["TINYFISH_API_KEY", "MOCK_SITE_BASE_URL"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Missing required environment values: {', '.join(missing)}")
        return 2

    dummy_url = os.environ["MOCK_SITE_BASE_URL"].rstrip("/") + "/mock/form"
    dummy_goal = """On this page, fill the demo form with exactly these fake values:
- Full name: "Savitri Devi"
- Age: "72"
- State: "Delhi"
- Mobile number: "9876543210"
Leave the Approval code field empty. Do NOT click Submit.
When every field is filled, stop and return JSON:
{"filled": {"full_name": "...", "age": "...", "state": "...", "phone": "..."}, "submitted": false, "problems": []}"""
    discovery_goal = """Open the myScheme website and look for the "Find schemes for you"
flow. Do not apply, submit, log in, or leave the site. If a CAPTCHA, OTP, or login
appears, stop. Return JSON with this exact shape:
{"schemes": [{"name": "...", "description": "...", "scheme_page_url": "..."}], "problems": []}"""

    async with httpx.AsyncClient(timeout=60) as client:
        print("dummy_form:")
        print(json.dumps(await run_agent(client, dummy_url, dummy_goal), indent=2))
        print("myscheme:")
        print(
            json.dumps(
                await run_agent(
                    client, "https://www.myscheme.gov.in/", discovery_goal
                ),
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
