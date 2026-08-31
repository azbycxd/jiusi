from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as api
from agent.orchestrator import OrderFactsOrchestrator
from decision.errors import ModelTimeoutError
from decision.model import FakeDecisionModel
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import ToolResult


def _install(monkeypatch, responses, client=None):
    tool = OrderFactsTool(client or FakeMarketClient({}))
    monkeypatch.setattr(api, "orchestrator", OrderFactsOrchestrator(registry=ToolRegistry([tool]), decision_model=FakeDecisionModel(responses)))


def _call_tool():
    return {"action": "CALL_TOOL", "tool_name": "get_order_facts", "tool_arguments": {"outTradeNo": "202608240001"}}


def test_http_missing_auth_and_blank_message_follow_public_safe_contract(monkeypatch):
    _install(monkeypatch, [{"action": "HANDOFF", "missing_information": ["no task"]}])
    client = TestClient(api.app)
    assert client.post("/v1/chat", json={"session_id": "a", "message": "订单状态"}).status_code == 401
    blank = client.post("/v1/chat", headers={"X-Authenticated-User-Id": "trusted"}, json={"session_id": "b", "message": "   "})
    assert blank.status_code == 200 and blank.json()["status"] == "HANDOFF"


def test_http_java_failure_is_bounded_and_safe(monkeypatch):
    class DownClient:
        def __init__(self): self.calls = 0
        def get_order_facts(self, auth, out_trade_no):
            self.calls += 1
            return ToolResult.infrastructure_failure("TOOL_CONNECTION_ERROR", "down", retryable=True, source="test")
    down = DownClient()
    _install(monkeypatch, [_call_tool()], down)
    response = TestClient(api.app).post("/v1/chat", headers={"X-Authenticated-User-Id": "trusted"}, json={"session_id": "java-down", "message": "订单状态"})
    assert response.status_code == 200 and response.json()["status"] == "HANDOFF" and down.calls == 2
    assert "TOOL_CONNECTION_ERROR" not in response.text


def test_http_provider_retry_and_terminal_failure_are_safe(monkeypatch):
    class TimeoutThenAnswer:
        def __init__(self): self.calls = 0
        def decide(self, context):
            self.calls += 1
            if self.calls == 1: raise ModelTimeoutError()
            return {"action": "ANSWER", "final_answer": "能力说明", "used_evidence": []}
    class AlwaysTimeout:
        def decide(self, context): raise ModelTimeoutError()
    monkeypatch.setattr(api, "orchestrator", OrderFactsOrchestrator(registry=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]), decision_model=TimeoutThenAnswer()))
    client = TestClient(api.app)
    recovered = client.post("/v1/chat", headers={"X-Authenticated-User-Id": "trusted"}, json={"session_id": "recover", "message": "你会什么？"})
    assert recovered.status_code == 200 and recovered.json()["status"] == "FINISHED"
    monkeypatch.setattr(api, "orchestrator", OrderFactsOrchestrator(registry=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]), decision_model=AlwaysTimeout()))
    terminal = client.post("/v1/chat", headers={"X-Authenticated-User-Id": "trusted"}, json={"session_id": "terminal", "message": "你会什么？"})
    assert terminal.status_code == 200 and terminal.json()["status"] == "HANDOFF" and "MODEL_TIMEOUT" not in terminal.text
