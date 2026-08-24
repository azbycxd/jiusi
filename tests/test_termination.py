from agent.state import AgentState, AgentStatus
from agent.termination import TerminationPolicy


def test_max_iterations_handoffs_instead_of_looping() -> None:
    state = AgentState(session_id="s-1", authenticated_user_id="trusted-user")
    state.control.iteration_count = state.control.max_iterations
    assert TerminationPolicy.enforce(state) is True
    assert state.status is AgentStatus.HANDOFF
    assert state.needs_human is True
