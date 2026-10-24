import asyncio
import json
import re
from typing import Any

import httpx

from .base import BrowserAgent, CancelResult, RunResult


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED"}
HUMAN_SIGNALS = {"captcha", "otp", "login", "blocked"}


class TinyFishAgent(BrowserAgent):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://agent.tinyfish.ai",
        poll_interval: float = 2.0,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("TinyFish API key is required")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }
        self.poll_interval = poll_interval
        self.timeout_seconds = timeout_seconds
        self._client = client
        self._owned_client: httpx.AsyncClient | None = None

    async def run(self, url: str, goal: str) -> RunResult:
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.base_url}/v1/automation/run-async",
                headers=self.headers,
                json={"url": url, "goal": goal},
            )
            if response.is_error:
                return self._api_error(response, "")
            run_id = response.json().get("run_id")
            if not isinstance(run_id, str) or not run_id:
                return RunResult(False, "", error="TinyFish did not return a run_id")

            deadline = asyncio.get_running_loop().time() + self.timeout_seconds
            latest: dict[str, Any] = {}
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(self.poll_interval)
                status_response = await client.get(
                    f"{self.base_url}/v1/runs/{run_id}", headers=self.headers
                )
                if status_response.is_error:
                    return self._api_error(status_response, run_id)
                latest = status_response.json()
                if latest.get("status") in TERMINAL_STATUSES:
                    return self._run_result(run_id, latest)

            cancel = await self.cancel(run_id)
            final_response = await client.get(
                f"{self.base_url}/v1/runs/{run_id}", headers=self.headers
            )
            if final_response.is_error:
                return RunResult(
                    False,
                    run_id,
                    error=f"watchdog expired; cancellation status: {cancel.status}",
                )
            final = final_response.json()
            if final.get("status") in TERMINAL_STATUSES:
                return self._run_result(run_id, final)
            return RunResult(
                False,
                run_id,
                error=f"watchdog expired; cancellation status: {cancel.status}",
            )
        except (httpx.HTTPError, ValueError, KeyError) as error:
            return RunResult(False, "", error=f"TinyFish request failed: {error}")

    async def cancel(self, run_id: str) -> CancelResult:
        client = await self._get_client()
        try:
            response = await client.post(
                f"{self.base_url}/v1/runs/{run_id}/cancel", headers=self.headers
            )
            if response.is_error:
                error = self._error_message(response)
                return CancelResult("FAILED", error)
            body = response.json()
            return CancelResult(
                str(body.get("status", "UNKNOWN")), body.get("message")
            )
        except httpx.HTTPError as error:
            return CancelResult("UNKNOWN", f"Cancellation request failed: {error}")

    async def aclose(self) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()
            self._owned_client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._owned_client = httpx.AsyncClient(timeout=60.0)
            self._client = self._owned_client
        return self._client

    def _run_result(self, run_id: str, run: dict[str, Any]) -> RunResult:
        result = run.get("result")
        error = run.get("error")
        status = run.get("status")
        if status == "COMPLETED":
            if not isinstance(result, dict):
                return RunResult(
                    False,
                    run_id,
                    final_text=self._result_text(result),
                    screenshot_url=self._screenshot(run),
                    streaming_url=run.get("streaming_url"),
                    error="TinyFish completed without a JSON result object",
                )
            problems = self._problems(result)
            needs_human = self._human_signal(problems)
            if needs_human:
                return RunResult(
                    False,
                    run_id,
                    final_text=json.dumps(result, ensure_ascii=False),
                    screenshot_url=self._screenshot(run),
                    streaming_url=run.get("streaming_url"),
                    error="The website requires human action",
                    needs_human=needs_human,
                )
            reported = result.get("filled")
            return RunResult(
                True,
                run_id,
                reported_fields=self._string_fields(reported),
                final_text=json.dumps(result, ensure_ascii=False),
                screenshot_url=self._screenshot(run),
                streaming_url=run.get("streaming_url"),
                error="; ".join(problems) if problems else None,
            )

        if status == "CANCELLED":
            return RunResult(
                False,
                run_id,
                final_text=self._result_text(result),
                screenshot_url=self._screenshot(run),
                streaming_url=run.get("streaming_url"),
                error="TinyFish run was cancelled",
            )
        return RunResult(
            False,
            run_id,
            final_text=self._result_text(result),
            screenshot_url=self._screenshot(run),
            streaming_url=run.get("streaming_url"),
            error=self._run_error(error) or f"TinyFish run ended with {status}",
            needs_human=(
                "blocked"
                if isinstance(error, dict)
                and error.get("category") == "SITE_BLOCKED"
                else self._human_signal([self._run_error(error)])
            ),
        )

    def _api_error(self, response: httpx.Response, run_id: str) -> RunResult:
        message = self._error_message(response)
        if response.status_code == 401:
            message = "TinyFish service is not set up"
        elif response.status_code == 402:
            message = "TinyFish wallet has insufficient credits"
        return RunResult(False, run_id, error=message)

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            body = response.json()
            error = body.get("error", body)
            return str(error.get("message") or error.get("code") or response.text)
        except (ValueError, AttributeError):
            return response.text or f"HTTP {response.status_code}"

    @staticmethod
    def _run_error(error: Any) -> str | None:
        if isinstance(error, dict):
            return str(error.get("message") or error.get("code") or "") or None
        return str(error) if error else None

    @staticmethod
    def _result_text(result: Any) -> str | None:
        return json.dumps(result, ensure_ascii=False) if result is not None else None

    @staticmethod
    def _string_fields(fields: Any) -> dict[str, str] | None:
        if not isinstance(fields, dict):
            return None
        return {str(key): str(value) for key, value in fields.items()}

    @staticmethod
    def _problems(result: dict[str, Any]) -> list[str]:
        problems = result.get("problems", [])
        if not isinstance(problems, list):
            return [str(problems)]
        return [str(problem) for problem in problems]

    @staticmethod
    def _human_signal(values: list[str | None]) -> str | None:
        text = " ".join(value or "" for value in values).lower()
        for signal in HUMAN_SIGNALS:
            if re.search(rf"\b{signal}\b", text):
                return signal
        return None

    @staticmethod
    def _screenshot(run: dict[str, Any]) -> str | None:
        steps = run.get("steps")
        if not isinstance(steps, list):
            return None
        for step in reversed(steps):
            if isinstance(step, dict) and step.get("screenshot"):
                return str(step["screenshot"])
        return None
