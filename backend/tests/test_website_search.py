import json
import unittest

import httpx

from backend.schemas import WebsiteResolutionOutput
from backend.website_search import (
    GeminiWebsiteSearch,
    WebsiteSearchConfigurationError,
    WebsiteSearchError,
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


def candidate_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class WebsiteSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_gemini_google_search_grounding_and_validates_output(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json=candidate_response(json.dumps(VALID_OUTPUT)),
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
        self.assertEqual(
            requests[0].url.path,
            "/v1beta/models/gemini-3.8-flash:generateContent",
        )
        self.assertEqual(requests[0].headers["x-goog-api-key"], "test-key")
        body = json.loads(requests[0].content)
        self.assertEqual(body["tools"], [{"google_search": {}}])
        self.assertEqual(
            body["generationConfig"]["responseMimeType"], "application/json"
        )
        prompt = body["contents"][0]["parts"][0]["text"]
        self.assertIn("untrusted data", prompt)
        self.assertIn("National Scholarship Portal", prompt)

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
                json=candidate_response("not JSON"),
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with self.assertRaisesRegex(WebsiteSearchError, "invalid candidate"):
                await search.resolve("National Scholarship Portal")

    async def test_http_errors_are_reported_without_leaking_response_body(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, text="private provider error detail")

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as client:
            search = GeminiWebsiteSearch(
                "test-key", "gemini-3.8-flash", client=client
            )
            with self.assertRaisesRegex(WebsiteSearchError, "HTTP 429") as error:
                await search.resolve("National Scholarship Portal")

        self.assertNotIn("private provider error detail", str(error.exception))


if __name__ == "__main__":
    unittest.main()
