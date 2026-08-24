from agent.state import AgentState


class SessionMemory:
    """In-process session memory solely for demonstrating task resumption."""

    def __init__(self) -> None:
        self._states: dict[str, AgentState] = {}

    def save_state(self, session_id: str, state: AgentState) -> None:
        self._states[session_id] = state.model_copy(deep=True)

    def load_state(self, session_id: str) -> AgentState | None:
        state = self._states.get(session_id)
        return state.model_copy(deep=True) if state else None
