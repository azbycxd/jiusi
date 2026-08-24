from agent.state import AgentState, AgentStatus, Intent


def test_state_has_separated_capability_context_and_control() -> None:
    state = AgentState(session_id="s-1", authenticated_user_id="trusted-user")
    assert state.capability.allowed_tools == ("get_order_diagnosis",)
    assert state.intent is Intent.UNKNOWN
    assert state.status is AgentStatus.RUNNING
    assert state.authenticated_user_id == "trusted-user"
