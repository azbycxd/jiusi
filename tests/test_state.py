import pytest

from agent.state import AgentState, AgentStatus, Intent, Observation
from memory.session_memory import SessionMemory
from tools.schemas import Evidence, ToolResult


def test_state_has_separated_capability_context_and_control() -> None:
    state = AgentState(session_id="s-1", authenticated_user_id="trusted-user")
    assert state.capability.allowed_tools == ("get_order_facts",)
    assert state.intent is Intent.UNKNOWN
    assert state.status is AgentStatus.RUNNING
    assert state.authenticated_user_id == "trusted-user"


def test_session_memory_isolates_states_by_session_id() -> None:
    memory = SessionMemory()
    first = AgentState(session_id="session-a", authenticated_user_id="user-a")
    second = AgentState(session_id="session-b", authenticated_user_id="user-b")
    first.context.out_trade_no = "order-a"
    second.context.out_trade_no = "order-b"

    memory.save_state(first.session_id, first)
    memory.save_state(second.session_id, second)

    restored_first = memory.load_state("session-a")
    restored_second = memory.load_state("session-b")

    assert restored_first is not None
    assert restored_second is not None
    assert restored_first.context.out_trade_no == "order-a"
    assert restored_second.context.out_trade_no == "order-b"
    assert restored_first.authenticated_user_id == "user-a"
    assert restored_second.authenticated_user_id == "user-b"


def test_observation_requires_successful_result_and_evidence_matching_data() -> None:
    successful = ToolResult(
        success=True,
        data={"order": {"status": "CLOSE"}},
        evidence=[Evidence(kind="order.status", value="CLOSE", source="test")],
        source="test",
    )
    observation = Observation.from_successful_tool_result("get_order_facts", successful)
    assert observation.tool_name == "get_order_facts"
    assert observation.evidence[0].kind == "get_order_facts.order.status"

    failed = ToolResult.infrastructure_failure("TOOL_TIMEOUT", "", retryable=True, source="test")
    with pytest.raises(ValueError, match="Failed ToolResult"):
        Observation.from_successful_tool_result("get_order_facts", failed)

    with pytest.raises(ValueError, match="match normalized observation data"):
        Observation(
            tool_name="get_order_facts",
            data={"order": {"status": "CLOSE"}},
            evidence=[Evidence(kind="get_order_facts.order.status", value="OPEN", source="test")],
        )
