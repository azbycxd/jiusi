import json
import logging

from agent.orchestrator import OrderDiagnosisOrchestrator
from agent.state import AgentState, AgentStatus
from tools.java_market_client import GetOrderDiagnosisTool, JavaMarketClient
from tools.schemas import ToolResult


def test_phase1_success_path_records_structured_trace(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    state = OrderDiagnosisOrchestrator().handle_message(
        "trace-session", "trusted-user", "我的订单 202608240001 为什么还没有拼团成功？"
    )
    assert state.status is AgentStatus.FINISHED
    assert state.diagnosis_code == "GROUP_IN_PROGRESS"
    events = [json.loads(record.message) for record in caplog.records]
    assert len(events) == 3
    for event in events:
        assert set(event) == {
            "trace_id", "session_id", "stage", "action", "tool_name", "tool_success",
            "error_code", "duration_ms", "iteration_count", "tool_call_count",
        }
    assert events[-2]["tool_name"] == "get_order_diagnosis"
    assert events[-2]["tool_success"] is True
    assert events[-1]["stage"] == "FINISHED"
    assert events[-1]["action"] == "persist_state"


def test_tool_identity_boundary_and_allowlist() -> None:
    assert "authenticated_user_id" not in GetOrderDiagnosisTool.run.__annotations__
    assert "user_id" not in JavaMarketClient.get_order_diagnosis.__annotations__
    assert "auth" in JavaMarketClient.get_order_diagnosis.__annotations__
    assert OrderDiagnosisOrchestrator().registry.allowed_names == ("get_order_diagnosis",)


def test_actual_termination_limits_and_error_classification() -> None:
    agent = OrderDiagnosisOrchestrator()
    iteration = AgentState(session_id="iteration", authenticated_user_id="trusted-user")
    iteration.control.max_iterations = 1
    agent.memory.save_state(iteration.session_id, iteration)
    assert agent.handle_message("iteration", "trusted-user", "查询拼团订单 202608240001").status is AgentStatus.HANDOFF

    calls = AgentState(session_id="calls", authenticated_user_id="trusted-user")
    calls.control.max_tool_calls = 1
    calls.control.max_retries = 5
    agent.memory.save_state(calls.session_id, calls)
    terminal = agent.handle_message("calls", "trusted-user", "查询拼团订单 202608240005")
    assert terminal.status is AgentStatus.HANDOFF
    assert terminal.retry_count == 1
    assert terminal.tool_call_count == 1

    retryable = ToolResult.infrastructure_failure("TEMP", "temporary", retryable=True, source="test")
    business_failure = ToolResult(success=False, error_code="NOT_FOUND", message="not found", source="test")
    assert retryable.success is False and retryable.retryable is True
    assert business_failure.success is False and business_failure.retryable is False
