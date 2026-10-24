from .base import BrowserAgent
from .mock_agent import MockBrowserAgent
from .tinyfish_agent import TinyFishAgent
from mock_site.store import MockStore


def create_browser_agent(
    mode: str,
    submission_store: MockStore,
    tinyfish_api_key: str,
    tinyfish_base_url: str,
) -> BrowserAgent:
    if mode == "mock":
        return MockBrowserAgent(submission_store)
    if mode == "tinyfish":
        if not tinyfish_api_key:
            raise ValueError(
                "BROWSER_AGENT=tinyfish requires TINYFISH_API_KEY in .env"
            )
        return TinyFishAgent(tinyfish_api_key, base_url=tinyfish_base_url)
    raise ValueError("BROWSER_AGENT must be either 'mock' or 'tinyfish'")
