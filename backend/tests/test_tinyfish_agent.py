import unittest

import httpx

from backend.agents.tinyfish_agent import TinyFishAgent


class TinyFishAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_polling_returns_fields_live_view_and_screenshot(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.url.path.endswith("/run-async"):
                return httpx.Response(200, json={"run_id": "run-1"})
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
                    "steps": [{"screenshot": "https://shot.example/1"}],
                },
            )

        client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="https://agent.test"
        )
        agent = TinyFishAgent("test-key", base_url="https://agent.test", poll_interval=0, client=client)
        result = await agent.run("https://demo.example/form", "fill")
        await client.aclose()

        self.assertTrue(result.ok)
        self.assertEqual(result.reported_fields["age"], "72")
        self.assertEqual(result.screenshot_url, "https://shot.example/1")
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


if __name__ == "__main__":
    unittest.main()
