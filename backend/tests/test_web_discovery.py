import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.planner import PlannerResult
from backend.schemas import TaskState, WebsiteResolutionOutput
from backend.task_store import TaskStore
from backend.website_search import (
    WebsiteSearchError,
    WebsiteSearchRateLimitError,
)
from mock_site.store import MockStore


class WebPlanner:
    async def plan(self, transcript, language, flows, values) -> PlannerResult:
        return PlannerResult(
            flow_id="web_discovery",
            values={"site_name": "National Scholarship Portal"},
            missing=[],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


class WebsiteAgent:
    def __init__(self, *results: RunResult) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str]] = []
        self.search_queries: list[str] = []

    async def resolve(self, site_name: str) -> WebsiteResolutionOutput:
        self.search_queries.append(site_name)
        result = self.results.pop(0)
        if not result.ok or not result.final_text:
            raise WebsiteSearchError("Search returned no candidate response.")
        return WebsiteResolutionOutput.model_validate_json(result.final_text)

    async def run(self, url: str, goal: str) -> RunResult:
        self.calls.append((url, goal))
        return self.results.pop(0)

    async def cancel(self, run_id: str) -> CancelResult:
        return CancelResult("CANCELLED")


class RateLimitedWebsiteSearch:
    async def resolve(self, site_name: str) -> WebsiteResolutionOutput:
        raise WebsiteSearchRateLimitError(
            "Gemini Search is rate- or quota-limited (HTTP 429)."
        )


def run_result(payload: dict, run_id: str) -> RunResult:
    return RunResult(True, run_id, final_text=json.dumps(payload))


class WebDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def make_orchestrator(
        self, agent: WebsiteAgent, website_search=None
    ) -> Orchestrator:
        return Orchestrator(
            TaskStore(),
            agent=agent,
            submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
            planner=WebPlanner(),
            website_search=website_search or agent,
        )

    @staticmethod
    async def wait_for_phase(orchestrator: Orchestrator, task_id: str, phase: str):
        for _ in range(300):
            task = orchestrator.store.get(task_id)
            if task is not None and task.web_phase == phase:
                return task
            if task is not None and task.state in {
                TaskState.COULD_NOT_FINISH,
                TaskState.OUTCOME_UNKNOWN,
            }:
                return task
            await asyncio.sleep(0.01)
        raise AssertionError(f"task did not reach web phase {phase}")

    def test_high_confidence_official_candidate_then_read_only_answer(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent(
                run_result(
                    {
                        "candidates": [
                            {
                                "name": "National Scholarship Portal",
                                "url": "https://scholarships.gov.in/",
                                "reason": "The search result is on the named government portal.",
                                "confidence": "high",
                            }
                        ],
                        "problems": [],
                    },
                    "site-search",
                ),
                run_result(
                    {
                        "answer": "Renewal applicants should check the current portal notice.",
                        "sources": [
                            {
                                "name": "Renewal Notice",
                                "url": "https://scholarships.gov.in/notices/renewal?ref=search",
                            }
                        ],
                    },
                    "site-read",
                ),
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task(
                "Find information on a public website", "en", "web"
            )
            task = await self.wait_for_phase(orchestrator, task.task_id, "question")

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(task.flow_id, "web_discovery")
            self.assertEqual(task.selected_site_url, "https://scholarships.gov.in/")
            self.assertEqual(agent.calls, [])
            self.assertEqual(agent.search_queries, ["National Scholarship Portal"])

            task = await orchestrator.answer(
                task.task_id, "What is the renewal notice?"
            )

            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(task.web_answer, "Renewal applicants should check the current portal notice.")
            self.assertEqual(
                task.web_sources[0].url,
                "https://scholarships.gov.in/notices/renewal",
            )
            self.assertEqual(len(agent.calls), 1)
            selected_url, research_goal = agent.calls[0]
            self.assertEqual(selected_url, "https://scholarships.gov.in/")
            self.assertIn("Do not log in", research_goal)
            self.assertIn("exact selected hostname", research_goal)
            self.assertIn("What is the renewal notice?", research_goal)
            self.assertEqual(
                orchestrator._history[task.task_id][-1].data["web_sources"][0]["url"],
                "https://scholarships.gov.in/notices/renewal",
            )

        asyncio.run(scenario())

    def test_ambiguous_candidates_require_user_selection_before_opening_site(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent(
                run_result(
                    {
                        "candidates": [
                            {
                                "name": "Scholarship Information",
                                "url": "https://scholarship-info.example/",
                                "reason": "A third-party information page.",
                                "confidence": "medium",
                            },
                            {
                                "name": "National Scholarship Portal",
                                "url": "https://scholarships.gov.in/",
                                "reason": "Government domain shown in the result.",
                                "confidence": "high",
                            },
                        ],
                        "problems": [],
                    },
                    "site-search",
                ),
                run_result(
                    {
                        "answer": "The portal notice has the details.",
                        "sources": [
                            {
                                "name": "Notice",
                                "url": "https://scholarships.gov.in/notice",
                            }
                        ],
                    },
                    "site-read",
                ),
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find a site", "en", "web")
            task = await self.wait_for_phase(orchestrator, task.task_id, "site_choice")
            event = orchestrator._history[task.task_id][-1]

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(len(agent.calls), 0)
            self.assertEqual(agent.search_queries, ["National Scholarship Portal"])
            self.assertEqual(len(event.data["candidates"]), 2)
            self.assertIn("will not open one", event.message_en)

            task = await orchestrator.answer(task.task_id, "2")
            self.assertEqual(task.web_phase, "question")
            self.assertEqual(task.selected_site_url, "https://scholarships.gov.in/")
            self.assertEqual(len(agent.calls), 0)

            task = await orchestrator.answer(task.task_id, "Explain the notice")
            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(agent.calls[0][0], "https://scholarships.gov.in/")

        asyncio.run(scenario())

    def test_untrusted_urls_and_off_site_sources_are_rejected(self) -> None:
        self.assertIsNone(
            Orchestrator._safe_public_site_url("http://scholarships.gov.in/")
        )
        self.assertIsNone(
            Orchestrator._safe_public_site_url("https://127.0.0.1/")
        )
        self.assertIsNone(
            Orchestrator._safe_public_site_url("https://example.local/")
        )
        self.assertIsNone(
            Orchestrator._safe_public_site_url("https://user:pass@example.gov/")
        )
        self.assertIsNone(
            Orchestrator._safe_public_site_url(
                "https://other.example/source",
                expected_host="scholarships.gov.in",
            )
        )
        self.assertEqual(
            Orchestrator._safe_public_site_url("https://scholarships.gov.in/source"),
            "https://scholarships.gov.in/source",
        )

    def test_missing_match_asks_for_clarification_before_searching_again(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent(
                run_result({"candidates": [], "problems": ["No clear official result."]}, "search-1"),
                run_result(
                    {
                        "candidates": [
                            {
                                "name": "National Scholarship Portal",
                                "url": "https://scholarships.gov.in/",
                                "reason": "Official government domain.",
                                "confidence": "high",
                            }
                        ],
                        "problems": [],
                    },
                    "search-2",
                ),
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find a website", "en", "web")
            task = await self.wait_for_phase(orchestrator, task.task_id, "site_name")

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(len(agent.calls), 0)
            self.assertEqual(len(agent.search_queries), 1)
            self.assertIn("could not identify", task.clarifying_question_en)

            task = await orchestrator.answer(
                task.task_id, "National Scholarship Portal"
            )
            self.assertEqual(task.web_phase, "question")
            self.assertEqual(len(agent.calls), 0)
            self.assertEqual(len(agent.search_queries), 2)

        asyncio.run(scenario())

    def test_search_rate_limit_has_recoverable_specific_failure(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent()
            orchestrator = self.make_orchestrator(
                agent, website_search=RateLimitedWebsiteSearch()
            )
            task = await orchestrator.create_task(
                "Find a website", "en", "web"
            )
            task = await self.wait_for_phase(
                orchestrator, task.task_id, "site_name"
            )

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "website_search_rate_limited")
            self.assertIn("HTTP 429", task.error)
            self.assertIn("quota", task.error_hi.lower())
            self.assertEqual(agent.calls, [])
            result_event = orchestrator._history[task.task_id][-1]
            self.assertEqual(
                result_event.data["reason"], "website_search_rate_limited"
            )

        asyncio.run(scenario())

    def test_answer_without_a_same_site_source_is_not_reported_as_success(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent(
                run_result(
                    {
                        "candidates": [
                            {
                                "name": "National Scholarship Portal",
                                "url": "https://scholarships.gov.in/",
                                "reason": "Official government domain.",
                                "confidence": "high",
                            }
                        ],
                        "problems": [],
                    },
                    "site-search",
                ),
                run_result(
                    {
                        "answer": "An unsupported answer.",
                        "sources": [
                            {
                                "name": "Different site",
                                "url": "https://other.example/source",
                            }
                        ],
                    },
                    "site-read",
                ),
            )
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task("Find a site", "en", "web")
            task = await self.wait_for_phase(orchestrator, task.task_id, "question")
            task = await orchestrator.answer(task.task_id, "What is the policy?")

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "website_result_unverified")
            self.assertEqual(task.web_sources, [])

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
