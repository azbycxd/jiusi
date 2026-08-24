from dataclasses import dataclass

from agent.orchestrator import OrderDiagnosisOrchestrator
from agent.state import AgentStatus


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    messages: tuple[str, ...]
    expected_status: AgentStatus


V1_CASES = (
    EvalCase("case_001", ("我的拼团订单 202608240001 为什么还没成功？",), AgentStatus.FINISHED),
    EvalCase("case_002", ("我的拼团为什么没成功？",), AgentStatus.WAITING_USER),
    EvalCase("case_003", ("我的拼团为什么没成功？", "202608240001"), AgentStatus.FINISHED),
    EvalCase("case_004", ("查询订单 202608240004",), AgentStatus.FINISHED),
    EvalCase("case_005", ("查询订单 202608240005",), AgentStatus.HANDOFF),
    EvalCase("case_006", ("查询订单 202608240006",), AgentStatus.FAILED),
    EvalCase("case_007", ("查询订单 202608240007",), AgentStatus.HANDOFF),
    EvalCase("case_008", ("查询订单 202608240008",), AgentStatus.HANDOFF),
)


def run_v1_cases() -> dict[str, int]:
    metrics = {"task_success": 0, "tool_success": 0, "handoff": 0, "retry_count": 0}
    for case in V1_CASES:
        agent = OrderDiagnosisOrchestrator()
        state = None
        for message in case.messages:
            state = agent.handle_message(case.case_id, "eval-user", message)
        assert state is not None
        metrics["task_success"] += int(state.status == case.expected_status)
        metrics["tool_success"] += int(any(result.success for result in state.tool_results))
        metrics["handoff"] += int(state.status is AgentStatus.HANDOFF)
        metrics["retry_count"] += state.retry_count
    return metrics
