import json
import unittest

import httpx

from backend.flow_loader import load_flows
from backend.planner import (
    GeminiPlanner,
    PlannerConfigurationError,
    PlannerOutputError,
    PlannerResult,
)


VALID_PLAN = {
    "flow_id": "mock_scheme_application",
    "values": {"full_name": "Savitri Devi", "age": 72},
    "missing": ["state", "phone"],
    "language": "en",
    "clarifying_question_en": "Please provide the state and phone number.",
    "clarifying_question_hi": "कृपया राज्य और फ़ोन नंबर बताएं।",
}


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_uses_json_mode_and_validates_output(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [
                                {"type": "text", "text": json.dumps(VALID_PLAN)}
                            ],
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Fill the demo form", "en", list(load_flows().values()), {}
            )

        self.assertEqual(result, PlannerResult.model_validate(VALID_PLAN))
        self.assertEqual(requests[0].url.path, "/v1beta/interactions")
        self.assertEqual(requests[0].headers["x-goog-api-key"], "test-key")
        body = json.loads(requests[0].content)
        self.assertEqual(body["model"], "gemini-3.8-flash")
        self.assertEqual(body["response_format"]["mime_type"], "application/json")
        self.assertFalse(body["store"])
        self.assertIn("Never guess", body["input"])
        self.assertIn("web_discovery", body["input"])
        self.assertIn("never invent a URL", body["input"])
        self.assertNotIn("test-key", str(requests[0].url))

    async def test_invalid_json_is_retried_once(self) -> None:
        responses = iter(
            [
                httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [{"type": "text", "text": "not json"}],
                            }
                        ],
                    },
                ),
                httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [
                                    {"type": "text", "text": json.dumps(VALID_PLAN)}
                                ],
                            }
                        ]
                    },
                ),
            ]
        )
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return next(responses)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Fill the demo form", "en", list(load_flows().values()), {}
            )

        self.assertEqual(result.flow_id, "mock_scheme_application")
        self.assertEqual(request_count, 2)

    async def test_invalid_json_after_retry_is_reported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": "not json"}],
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            with self.assertRaises(PlannerOutputError):
                await planner.plan(
                    "Fill the demo form", "en", list(load_flows().values()), {}
                )

    async def test_missing_api_key_fails_without_making_a_request(self) -> None:
        planner = GeminiPlanner("", "gemini-3.8-flash")
        with self.assertRaisesRegex(PlannerConfigurationError, "LLM_API_KEY"):
            await planner.plan("Fill the demo form", "en", [], {})


if __name__ == "__main__":
    unittest.main()
