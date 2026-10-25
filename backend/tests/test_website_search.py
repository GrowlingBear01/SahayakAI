import json
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from backend.schemas import WebsiteResolutionOutput
from backend.website_search import (
    GeminiWebsiteSearch,
    WebsiteSearchConfigurationError,
    WebsiteSearchError,
    WebsiteSearchRateLimitError,
)


VALID_OUTPUT = {
    "candidates": [
        {
            "name": "National Scholarship Portal",
            "url": "https://scholarships.gov.in/",
            "reason": "Google Search results identify the government portal.",
            "confidence": "high",
        }
    ],
    "problems": [],
}


class WebsiteSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_gemini_google_search_grounding_and_validates_output(self) -> None:
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
                                {
                                    "type": "text",
                                    "text": json.dumps(VALID_OUTPUT),
                                }
                            ],
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            result = await search.resolve("National Scholarship Portal")

        self.assertEqual(
            result, WebsiteResolutionOutput.model_validate(VALID_OUTPUT)
        )
        self.assertEqual(requests[0].url.path, "/v1beta/interactions")
        self.assertEqual(requests[0].headers["x-goog-api-key"], "test-key")
        body = json.loads(requests[0].content)
        self.assertEqual(body["tools"], [{"type": "google_search"}])
        self.assertEqual(body["response_format"]["mime_type"], "application/json")
        self.assertFalse(body["store"])
        self.assertIn("untrusted data", body["input"])
        self.assertIn("National Scholarship Portal", body["input"])

    async def test_missing_key_fails_without_request(self) -> None:
        search = GeminiWebsiteSearch("", "gemini-3.8-flash")
        with self.assertRaisesRegex(
            WebsiteSearchConfigurationError, "LLM_API_KEY"
        ):
            await search.resolve("National Scholarship Portal")

    async def test_invalid_grounded_output_is_reported(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "steps": [
                        {
                            "type": "model_output",
                            "content": [{"type": "text", "text": "not JSON"}],
                        }
                    ],
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with self.assertRaisesRegex(WebsiteSearchError, "invalid candidate"):
                await search.resolve("National Scholarship Portal")

    async def test_rate_limit_retries_then_succeeds(self) -> None:
        requests: list[httpx.Request] = []
        responses = iter(
            [
                httpx.Response(429, headers={"Retry-After": "0"}),
                httpx.Response(
                    200,
                    json={
                        "status": "completed",
                        "steps": [
                            {
                                "type": "model_output",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(VALID_OUTPUT),
                                    }
                                ],
                            }
                        ],
                    },
                ),
            ]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return next(responses)

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with patch(
                "backend.website_search.asyncio.sleep", new_callable=AsyncMock
            ) as sleep:
                result = await search.resolve("National Scholarship Portal")

        self.assertEqual(len(requests), 2)
        sleep.assert_awaited_once_with(0.0)
        self.assertEqual(
            result, WebsiteResolutionOutput.model_validate(VALID_OUTPUT)
        )

    async def test_persistent_rate_limit_is_reported_without_leaking_body(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                429,
                text="private provider error detail",
                headers={"Retry-After": "0"},
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with patch(
                "backend.website_search.asyncio.sleep", new_callable=AsyncMock
            ):
                with self.assertRaisesRegex(
                    WebsiteSearchRateLimitError, "quota.*HTTP 429"
                ) as error:
                    await search.resolve("National Scholarship Portal")

        self.assertEqual(
            request_count, GeminiWebsiteSearch.MAX_RATE_LIMIT_RETRIES + 1
        )
        self.assertNotIn("private provider error detail", str(error.exception))

    async def test_long_retry_after_does_not_wait_or_retry(self) -> None:
        request_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal request_count
            request_count += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "3600"},
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with patch(
                "backend.website_search.asyncio.sleep", new_callable=AsyncMock
            ) as sleep:
                with self.assertRaises(WebsiteSearchRateLimitError):
                    await search.resolve("National Scholarship Portal")

        self.assertEqual(request_count, 1)
        sleep.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
