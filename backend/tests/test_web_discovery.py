import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.base import CancelResult, RunResult
from backend.orchestrator import Orchestrator
from backend.planner import PlannerResult
from backend.schemas import ApproveRequest, TaskState, WebsiteResolutionOutput
from backend.task_store import TaskStore
from backend.website_search import WebsiteSearchError
from mock_site.store import MockStore


class WebPlanner:
    async def plan(
        self, transcript, language, flows, values, conversation_history=()
    ) -> PlannerResult:
        return PlannerResult(
            flow_id="web_discovery",
            values={"site_name": "National Scholarship Portal"},
            missing=[],
            language="en",
            clarifying_question_en="",
            clarifying_question_hi="",
        )


class YouTubePlanner:
    def __init__(self, query: str = "Arijit Singh songs") -> None:
        self.query = query

    async def plan(
        self, transcript, language, flows, values, conversation_history=()
    ) -> PlannerResult:
        return PlannerResult(
            flow_id="web_discovery",
            values={"site_name": "YouTube", "web_query": self.query},
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


def run_result(payload: dict, run_id: str) -> RunResult:
    return RunResult(True, run_id, final_text=json.dumps(payload))


class WebDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def make_orchestrator(self, agent: WebsiteAgent) -> Orchestrator:
        return Orchestrator(
            TaskStore(),
            agent=agent,
            submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
            planner=WebPlanner(),
            website_search=agent,
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

    @staticmethod
    async def wait_for_approval(orchestrator: Orchestrator, task_id: str):
        for _ in range(300):
            task = orchestrator.store.get(task_id)
            if task is not None and task.state == TaskState.WAITING_FOR_APPROVAL:
                return task
            if task is not None and task.state in {
                TaskState.COULD_NOT_FINISH,
                TaskState.OUTCOME_UNKNOWN,
            }:
                return task
            await asyncio.sleep(0.01)
        raise AssertionError("task did not reach approval")

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
                "Find information on a public website", "en", "auto"
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

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(agent.calls, [])
            self.assertEqual(task.approval_type, "web")
            self.assertIn("What is the renewal notice?", orchestrator._history[task.task_id][-1].data["action_en"])

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
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
            self.assertTrue(
                any(
                    event.data.get("browser_started") is True
                    for event in orchestrator._history[task.task_id]
                )
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
            task = await orchestrator.create_task("Find a site", "en", "auto")
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
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(agent.calls, [])
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )
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
            task = await orchestrator.create_task("Find a website", "en", "auto")
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
            task = await orchestrator.create_task("Find a site", "en", "auto")
            task = await self.wait_for_phase(orchestrator, task.task_id, "question")
            task = await orchestrator.answer(task.task_id, "What is the policy?")
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.COULD_NOT_FINISH)
            self.assertEqual(task.reason, "website_result_unverified")
            self.assertEqual(task.web_sources, [])

        asyncio.run(scenario())

    def test_song_search_requires_approval_and_returns_safe_youtube_links(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent(
                run_result(
                    {
                        "answer": "These public videos match the requested artist.",
                        "sources": [
                            {
                                "name": "YouTube search results",
                                "url": "https://www.youtube.com/results?search_query=arijit",
                            }
                        ],
                        "media": [
                            {
                                "title": "Example official song",
                                "url": "https://www.youtube.com/watch?v=abcdefghijk&feature=share",
                            },
                            {
                                "title": "Off-site result",
                                "url": "https://attacker.example/watch?v=abcdefghijk",
                            },
                            {
                                "title": "Malformed video id",
                                "url": "https://www.youtube.com/watch?v=short",
                            },
                        ],
                    },
                    "youtube-results",
                ),
            )
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
                planner=YouTubePlanner(),
                website_search=agent,
            )
            task = await orchestrator.create_task("Search Arijit Singh songs", "en")
            task = await self.wait_for_approval(orchestrator, task.task_id)

            self.assertEqual(task.web_query, "Arijit Singh songs")
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(agent.calls, [])
            approval = orchestrator._history[task.task_id][-1].data
            self.assertEqual(approval["approval_type"], "web")
            self.assertIn("Arijit Singh songs", approval["action_en"])
            self.assertIn("will not", approval["data_notice_en"])

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.DONE)
            self.assertIn("Do not click play or start media", agent.calls[0][1])
            self.assertEqual(
                [media.url for media in task.web_media],
                ["https://www.youtube.com/watch?v=abcdefghijk"],
            )

        asyncio.run(scenario())

    def test_youtube_media_url_requires_a_public_video_watch_url(self) -> None:
        self.assertEqual(
            Orchestrator._safe_youtube_media_url(
                "https://www.youtube.com/watch?v=abcdefghijk&feature=share"
            ),
            "https://www.youtube.com/watch?v=abcdefghijk",
        )
        for url in (
            "http://www.youtube.com/watch?v=abcdefghijk",
            "https://www.youtube.com.evil.example/watch?v=abcdefghijk",
            "https://www.youtube.com/watch?v=short",
            "https://www.youtube.com/watch?v=abcdefghijk&v=zyxwvutsrqp",
        ):
            self.assertIsNone(Orchestrator._safe_youtube_media_url(url))
        self.assertEqual(
            Orchestrator._safe_youtube_media_url(
                "https://youtu.be/abcdefghijk?si=share"
            ),
            "https://www.youtube.com/watch?v=abcdefghijk",
        )

    def test_explicit_youtube_search_reaches_approval_without_planner_or_search(self) -> None:
        async def scenario() -> None:
            class UnexpectedPlanner:
                async def plan(
                    self, transcript, language, flows, values, conversation_history=()
                ):
                    raise AssertionError("explicit YouTube searches bypass the planner")

            agent = WebsiteAgent()
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
                planner=UnexpectedPlanner(),
                website_search=agent,
            )
            task = await orchestrator.create_task(
                "go to youtube and search arijit songs", "en"
            )
            task = await self.wait_for_approval(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.values["site_name"], "YouTube")
            self.assertEqual(task.web_query, "arijit songs")
            self.assertEqual(
                task.selected_site_url, "https://www.youtube.com/"
            )
            self.assertEqual(agent.calls, [])
            self.assertEqual(agent.search_queries, [])
            self.assertTrue(
                any(
                    event.data.get("action") == "Preparing YouTube search"
                    for event in orchestrator._history[task.task_id]
                )
            )

        asyncio.run(scenario())

    def test_explicit_https_url_skips_gemini_and_requires_approval(self) -> None:
        async def scenario() -> None:
            class UnexpectedPlanner:
                async def plan(
                    self, transcript, language, flows, values, conversation_history=()
                ):
                    raise AssertionError("explicit website mode must bypass Gemini")

            agent = WebsiteAgent(
                run_result(
                    {
                        "answer": "The shipping page lists the available delivery options.",
                        "sources": [
                            {
                                "name": "Shipping",
                                "url": "https://example.org/shipping",
                            }
                        ],
                    },
                    "site-read",
                )
            )
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
                planner=UnexpectedPlanner(),
                website_search=agent,
            )
            task = await orchestrator.create_task(
                "Find shipping fees at https://example.org/help", "en", "web"
            )
            task = await self.wait_for_approval(orchestrator, task.task_id)

            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.selected_site_url, "https://example.org/help")
            self.assertEqual(task.web_query, "shipping fees")
            self.assertEqual(agent.search_queries, [])
            self.assertEqual(agent.calls, [])
            candidate = task.web_candidates[0]
            self.assertEqual(candidate.confidence, "low")
            self.assertIn("not independently verified", candidate.reason)

            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(agent.calls[0][0], "https://example.org/help")
            self.assertIn("shipping fees", agent.calls[0][1])

        asyncio.run(scenario())

    def test_web_mode_requests_safe_url_and_search_question_before_approval(self) -> None:
        async def scenario() -> None:
            class UnexpectedPlanner:
                async def plan(
                    self, transcript, language, flows, values, conversation_history=()
                ):
                    raise AssertionError("explicit website mode must bypass Gemini")

            agent = WebsiteAgent()
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
                planner=UnexpectedPlanner(),
                website_search=agent,
            )
            task = await orchestrator.create_task("Explore a website", "en", "web")
            task = await self.wait_for_phase(orchestrator, task.task_id, "site_name")

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertIn("HTTPS", task.clarifying_question_en)
            self.assertEqual(agent.search_queries, [])

            with self.assertRaisesRegex(ValueError, "HTTPS"):
                await orchestrator.answer(task.task_id, "http://127.0.0.1/")

            task = await orchestrator.answer(
                task.task_id, "https://public.example.org/"
            )
            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertEqual(task.web_phase, "question")
            self.assertEqual(task.selected_site_url, "https://public.example.org/")
            self.assertEqual(agent.calls, [])
            self.assertEqual(agent.search_queries, [])

            task = await orchestrator.answer(task.task_id, "Find the contact page")
            self.assertEqual(task.state, TaskState.WAITING_FOR_APPROVAL)
            self.assertEqual(task.web_query, "Find the contact page")
            self.assertEqual(agent.calls, [])

        asyncio.run(scenario())

    def test_web_mode_rejects_unsafe_provided_url_before_approval(self) -> None:
        async def scenario() -> None:
            agent = WebsiteAgent()
            orchestrator = self.make_orchestrator(agent)
            task = await orchestrator.create_task(
                "Read https://127.0.0.1/admin", "en", "web"
            )
            task = await self.wait_for_phase(orchestrator, task.task_id, "site_name")

            self.assertEqual(task.state, TaskState.NEEDS_INFO)
            self.assertIsNone(task.selected_site_url)
            self.assertEqual(agent.calls, [])
            self.assertEqual(agent.search_queries, [])

        asyncio.run(scenario())

    def test_youtube_search_parser_requires_explicit_search_command(self) -> None:
        for text, expected in (
            ("go to youtube and search arijit songs", "arijit songs"),
            ("Search Arijit songs on YouTube", "Arijit songs"),
            ("find live concerts on youtube.com", "live concerts"),
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    Orchestrator._explicit_youtube_search_query(text), expected
                )
        self.assertIsNone(
            Orchestrator._explicit_youtube_search_query("I watch YouTube")
        )

    def test_user_provided_youtube_share_link_is_returned_for_manual_open(self) -> None:
        async def scenario() -> None:
            shared_link = "https://youtu.be/abcdefghijk?si=share"
            agent = WebsiteAgent(
                run_result(
                    {
                        "candidates": [
                            {
                                "name": "YouTube",
                                "url": "https://www.youtube.com/",
                                "reason": "Official video-sharing platform.",
                                "confidence": "high",
                            }
                        ],
                        "problems": [],
                    },
                    "site-search",
                )
            )
            orchestrator = Orchestrator(
                TaskStore(),
                agent=agent,
                submission_store=MockStore(Path(self.temp_dir.name) / "mock.db"),
                planner=YouTubePlanner(shared_link),
                website_search=agent,
            )
            task = await orchestrator.create_task(shared_link, "hi")
            task = await self.wait_for_approval(orchestrator, task.task_id)
            task = await orchestrator.approve(
                task.task_id,
                ApproveRequest(approval_id=task.approval_id),
            )

            self.assertEqual(task.state, TaskState.DONE)
            self.assertEqual(agent.calls, [])
            self.assertEqual(
                task.web_media[0].url,
                "https://www.youtube.com/watch?v=abcdefghijk",
            )
            self.assertEqual(task.web_media[0].title, "आपके अनुरोध का YouTube वीडियो")
            self.assertIn("आपके नियंत्रण", task.web_answer)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
