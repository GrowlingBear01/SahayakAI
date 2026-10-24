import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from backend.agents.factory import create_browser_agent
from backend.agents.mock_agent import MockBrowserAgent
from backend.agents.tinyfish_agent import TinyFishAgent
from mock_site.store import MockStore


class BrowserAgentFactoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = MockStore(Path(self.temp_dir.name) / "mock.db")

    def test_mock_mode_creates_mock_agent(self) -> None:
        agent = create_browser_agent("mock", self.store, "", "")
        self.assertIsInstance(agent, MockBrowserAgent)

    def test_tinyfish_mode_creates_tinyfish_agent(self) -> None:
        agent = create_browser_agent(
            "tinyfish",
            self.store,
            "test-key",
            "https://agent.example",
        )
        self.assertIsInstance(agent, TinyFishAgent)
        self.assertEqual(agent.base_url, "https://agent.example")

    def test_tinyfish_mode_requires_api_key_without_mock_fallback(self) -> None:
        with self.assertRaisesRegex(ValueError, "TINYFISH_API_KEY"):
            create_browser_agent(
                "tinyfish",
                self.store,
                "",
                "https://agent.example",
            )

    def test_unknown_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "BROWSER_AGENT"):
            create_browser_agent("other", self.store, "test-key", "")


if __name__ == "__main__":
    unittest.main()
