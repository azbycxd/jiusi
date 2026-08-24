from agent.state import AgentState, AgentStatus


class TerminationPolicy:
    """Central, finite execution policy. The orchestrator has no unbounded loop."""

    @staticmethod
    def enforce(state: AgentState) -> bool:
        if state.status is not AgentStatus.RUNNING:
            return True
        if state.iteration_count >= state.control.max_iterations:
            TerminationPolicy.handoff(state, "本次订单诊断步骤已达到上限，已转人工客服处理。")
            return True
        if state.tool_call_count >= state.control.max_tool_calls:
            TerminationPolicy.handoff(state, "本次查询次数已达到上限，已转人工客服处理。")
            return True
        return False

    @staticmethod
    def handoff(state: AgentState, answer: str) -> None:
        state.control.status = AgentStatus.HANDOFF
        state.control.needs_human = True
        state.control.final_answer = answer
