from agent.state import AgentState, AgentStatus, Intent
from memory.session_memory import SessionMemory


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
