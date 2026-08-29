"""Local facts-flow harness. It uses FakeMarketClient and never calls Java HTTP."""

from __future__ import annotations

import json

from agent.orchestrator import OrderFactsOrchestrator
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


def main() -> None:
    result = ToolResult(
        success=True,
        message="facts",
        data={
            "order": {"status": "CLOSE"},
            "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0, "valid_end_time": None},
            "activity": {"status": "EFFECTIVE"},
            "references": {"team_id": "team-1", "activity_id": 100123},
        },
        evidence=[Evidence(kind="order.status", value="CLOSE", source="fake_market")],
        source="fake_market",
    )
    client = FakeMarketClient({"202608240001": result})
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(client)]), compatibility_mode=True
    )
    state = agent.handle_message("facts-harness", "trusted-user", "查询订单 202608240001")
    print(json.dumps({
        "status": state.status.value,
        "answer": state.final_answer,
        "observations": [item.model_dump(mode="json") for item in state.observations],
        "tool_calls": state.tool_call_count,
    }, ensure_ascii=True))


if __name__ == "__main__":
    main()
