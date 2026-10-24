import os
from pathlib import Path

from .schemas import FlowConfig


FLOW_DIRECTORY = Path(__file__).parent / "flows"


def load_flows() -> dict[str, FlowConfig]:
    flows: dict[str, FlowConfig] = {}
    for path in sorted(FLOW_DIRECTORY.glob("*.json")):
        flow = FlowConfig.model_validate_json(path.read_text(encoding="utf-8"))
        if "${MOCK_SITE_BASE_URL}" in flow.url:
            base_url = os.getenv("MOCK_SITE_BASE_URL", "")
            if base_url:
                flow = flow.model_copy(
                    update={"url": flow.url.replace("${MOCK_SITE_BASE_URL}", base_url)}
                )
        if flow.id in flows:
            raise ValueError(f"duplicate flow id: {flow.id}")
        flows[flow.id] = flow
    return flows
