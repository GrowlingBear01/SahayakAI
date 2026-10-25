import json
import unittest

import httpx

from backend.flow_loader import load_flows
from backend.planner import (
    GeminiPlanner,
    PlannerConfigurationError,
    PlannerOutputError,
    PlannerRateLimitError,
    PlannerResult,
)
from backend.schemas import ConversationTurn


VALID_PLAN = {
    "action": "task",
    "flow_id": "mock_scheme_application",
    "values": {"full_name": "Savitri Devi", "age": 72},
    "missing": ["state", "phone"],
    "language": "en",
    "clarifying_question_en": "Please provide the state and phone number.",
    "clarifying_question_hi": "कृपया राज्य और फ़ोन नंबर बताएं।",
    "response_en": "",
    "response_hi": "",
}


def candidate_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class PlannerTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_uses_json_mode_and_validates_output(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json=candidate_response(json.dumps(VALID_PLAN)),
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Fill the demo form", "en", list(load_flows().values()), {}
            )

        self.assertEqual(result, PlannerResult.model_validate(VALID_PLAN))
        self.assertEqual(
            requests[0].url.path,
            "/v1beta/models/gemini-3.8-flash:generateContent",
        )
        self.assertEqual(requests[0].headers["x-goog-api-key"], "test-key")
        body = json.loads(requests[0].content)
        self.assertEqual(
            body["generationConfig"]["responseMimeType"], "application/json"
        )
        self.assertNotIn("responseSchema", body["generationConfig"])
        prompt = body["contents"][0]["parts"][0]["text"]
        self.assertIn("Never guess", prompt)
        self.assertIn("web_discovery", prompt)
        self.assertIn("Never invent a URL", prompt)
        self.assertIn("publicly available music or videos", prompt)
        self.assertIn("preserve that exact link", prompt)
        self.assertIn("YouTube as site_name", prompt)
        self.assertIn("web_query", prompt)
        self.assertIn('"conversation_history": []', prompt)
        self.assertNotIn("test-key", str(requests[0].url))

    async def test_invalid_json_is_retried_once(self) -> None:
        responses = iter(
            [
                httpx.Response(
                    200,
                    json=candidate_response("not json"),
                ),
                httpx.Response(
                    200,
                    json=candidate_response(json.dumps(VALID_PLAN)),
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
                json=candidate_response("not json"),
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

    async def test_rate_limit_is_reported_without_leaking_provider_response(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                429,
                json={"error": {"message": "private quota response"}},
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            with self.assertRaises(PlannerRateLimitError) as error:
                await planner.plan(
                    "Find schemes listed on myScheme",
                    "en",
                    list(load_flows().values()),
                    {},
                )

        self.assertNotIn("private quota response", str(error.exception))
        self.assertEqual(len(requests), 1)
        self.assertIn("gemini-3.8-flash", str(requests[0].url))

    async def test_unavailable_configured_model_falls_back_to_flash_lite(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if "gemini-3.8-flash" in str(request.url):
                return httpx.Response(503)
            return httpx.Response(
                200,
                json=candidate_response(json.dumps(VALID_PLAN)),
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Fill the demo form", "en", list(load_flows().values()), {}
            )

        self.assertEqual(result.flow_id, "mock_scheme_application")
        self.assertEqual(len(requests), 2)
        self.assertIn("gemini-3.8-flash", str(requests[0].url))
        self.assertIn("gemini-3.5-flash-lite", str(requests[1].url))

    async def test_read_timeout_on_configured_model_uses_fallback(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if "gemini-3.8-flash" in str(request.url):
                raise httpx.ReadTimeout("timed out", request=request)
            return httpx.Response(
                200,
                json=candidate_response(json.dumps(VALID_PLAN)),
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Fill the demo form", "en", list(load_flows().values()), {}
            )

        self.assertEqual(result.flow_id, "mock_scheme_application")
        self.assertEqual(len(requests), 2)
        self.assertIn("gemini-3.5-flash-lite", str(requests[1].url))

    async def test_conversation_history_is_passed_as_separate_context(self) -> None:
        request_context: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            request_context.update(json.loads(request.content))
            return httpx.Response(
                200,
                json=candidate_response(
                    json.dumps(
                        {
                            "action": "conversation",
                            "flow_id": None,
                            "values": {},
                            "missing": [],
                            "language": "en",
                            "clarifying_question_en": "",
                            "clarifying_question_hi": "",
                            "response_en": "Here is a warmer version.",
                            "response_hi": "यह थोड़ा अधिक आत्मीय रूप है।",
                        }
                    )
                ),
            )

        history = [
            ConversationTurn(role="user", text="Draft a thank-you note."),
            ConversationTurn(role="assistant", text="Who is it for?"),
        ]
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            planner = GeminiPlanner("test-key", "gemini-3.8-flash", client=client)
            result = await planner.plan(
                "Make it warmer.",
                "en",
                list(load_flows().values()),
                {},
                history,
            )

        self.assertEqual(result.action, "conversation")
        self.assertEqual(result.response_en, "Here is a warmer version.")
        self.assertEqual(
            json.loads(
                request_context["contents"][0]["parts"][0]["text"].split(
                    "Request context JSON:\n", 1
                )[1]
            )["conversation_history"],
            [turn.model_dump() for turn in history],
        )


if __name__ == "__main__":
    unittest.main()
