import unittest

import httpx

from backend.agents.tinyfish_agent import TinyFishAgent


class TinyFishAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_returns_fields_live_view_and_screenshot(self) -> None:
        requests: list[httpx.Request] = []
        progress: list[tuple[str | None, str | None]] = []
        poll_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal poll_count
            requests.append(request)
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-1"})
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(
                    200,
                    json={
                        "status": "RUNNING",
                        "streaming_url": "https://stream.example/run-1",
                        "steps": [{"action": "Opened the form"}],
                    },
                )
            return httpx.Response(
                200,
                json={
                    "status": "COMPLETED",
                    "result": {
                        "filled": {
                            "full_name": "Savitri Devi",
                            "age": 72,
                            "state": "Delhi",
                            "phone": "9876543210",
                        },
                        "submitted": False,
                        "problems": [],
                    },
                    "streaming_url": "https://stream.example/run-1",
                    "steps": [
                        {
                            "action": "Opened the form",
                            "screenshot": "https://shot.example/1",
                        }
                    ],
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent("test-key", base_url="https://agent.test", poll_interval=0, client=client)

        async def on_progress(url, action):
            progress.append((url, action))

        result = await agent.run_with_callback(
            "https://demo.example/form",
            "fill",
            None,
            on_progress,
        )
        await client.aclose()

        self.assertTrue(result.ok)
        self.assertEqual(result.reported_fields["age"], "72")
        self.assertEqual(result.screenshot_url, "https://shot.example/1")
        self.assertEqual(result.streaming_url, "https://stream.example/run-1")
        self.assertEqual(
            progress,
            [("https://stream.example/run-1", "Opened the form")],
        )
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[0].url.path, "/v1/automation/run-async")
        self.assertNotIn("test-key", requests[0].content.decode())

    async def test_maps_human_action_and_cancel_status(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-1"})
            if request.url.path.endswith("/cancel"):
                return httpx.Response(200, json={"status": "CANCELLED", "message": "done"})
            return httpx.Response(
                200,
                json={
                    "status": "FAILED",
                    "error": {"category": "SITE_BLOCKED", "message": "captcha detected"},
                    "steps": [],
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent("test-key", base_url="https://agent.test", poll_interval=0, client=client)
        result = await agent.run("https://demo.example/form", "fill")
        cancel = await agent.cancel("run-1")
        await client.aclose()

        self.assertFalse(result.ok)
        self.assertEqual(result.needs_human, "blocked")
        self.assertEqual(cancel.status, "CANCELLED")

    async def test_rechecks_after_watchdog_cancel(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-2"})
            if request.url.path.endswith("/cancel"):
                return httpx.Response(200, json={"status": "CANCELLED"})
            return httpx.Response(200, json={"status": "CANCELLED", "result": None})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent(
            "test-key",
            base_url="https://agent.test",
            poll_interval=0,
            timeout_seconds=0,
            client=client,
        )
        result = await agent.run("https://demo.example/form", "slow")
        await client.aclose()

        self.assertFalse(result.ok)
        self.assertIn("cancelled", result.error.lower())
        self.assertGreaterEqual(calls, 3)

    async def test_poll_http_error_cancels_and_confirms_terminal_status(self) -> None:
        calls: list[str] = []
        poll_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal poll_count
            calls.append(request.url.path)
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-503"})
            if request.url.path.endswith("/cancel"):
                return httpx.Response(200, json={"status": "CANCELLED"})
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(503, json={"error": "temporary"})
            return httpx.Response(200, json={"status": "CANCELLED"})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent(
            "test-key",
            base_url="https://agent.test",
            poll_interval=0,
            client=client,
        )
        result = await agent.run("https://demo.example/form", "fill")
        await client.aclose()

        self.assertEqual(result.run_id, "run-503")
        self.assertFalse(result.unresolved)
        self.assertEqual(
            calls,
            [
                "/v1/automation/run-async",
                "/v1/runs/run-503",
                "/v1/runs/run-503/cancel",
                "/v1/runs/run-503",
            ],
        )

    async def test_poll_transport_error_stays_unresolved_if_run_remains_active(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-active"})
            if request.url.path.endswith("/cancel"):
                return httpx.Response(200, json={"status": "UNKNOWN"})
            if calls.count("/v1/runs/run-active") == 1:
                raise httpx.ConnectError("poll connection lost")
            return httpx.Response(200, json={"status": "RUNNING"})

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent(
            "test-key",
            base_url="https://agent.test",
            poll_interval=0,
            client=client,
        )
        result = await agent.run("https://demo.example/form", "fill")
        await client.aclose()

        self.assertEqual(result.run_id, "run-active")
        self.assertTrue(result.unresolved)
        self.assertIn("status could not be checked", result.error)
        self.assertEqual(
            calls,
            [
                "/v1/automation/run-async",
                "/v1/runs/run-active",
                "/v1/runs/run-active/cancel",
                "/v1/runs/run-active",
            ],
        )


if __name__ == "__main__":
    unittest.main()
