from dataclasses import dataclass

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


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
    EvalCase("case_007", ("查询订单 202608240007",), AgentStatus.FAILED),
    EvalCase("case_008", ("查询订单 202608240008",), AgentStatus.HANDOFF),
)


def _facts_result() -> ToolResult:
    facts = {
        "order": {"status": "CLOSE"},
        "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0, "valid_end_time": None},
        "activity": {"status": "EFFECTIVE"},
        "references": {"team_id": "18781389", "activity_id": 100123},
    }
    return ToolResult(
        success=True,
        message="订单事实获取成功",
        data={"facts": facts},
        evidence=[Evidence(kind="order.status", value="CLOSE", source="fake_market")],
        source="fake_market",
    )


def _agent() -> OrderFactsOrchestrator:
    results = {
        "202608240001": _facts_result(),
        "202608240004": ToolResult(success=False, error_code="ORDER_NOT_FOUND_OR_NOT_AUTHORIZED", message="", source="fake_market"),
        "202608240005": ToolResult.infrastructure_failure("INTERNAL_SERVICE_ERROR", "", retryable=True, source="fake_market"),
        "202608240006": ToolResult.infrastructure_failure("INVALID_ARGUMENT", "", retryable=False, source="fake_market"),
        "202608240007": ToolResult.infrastructure_failure("TOOL_CONTRACT_MISMATCH", "", retryable=False, source="fake_market"),
        "202608240008": ToolResult.infrastructure_failure("TOOL_TIMEOUT", "", retryable=True, source="fake_market"),
    }
    return OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(FakeMarketClient(results))]), compatibility_mode=True
    )


def run_v1_cases() -> dict[str, int]:
    metrics = {"task_success": 0, "tool_success": 0, "handoff": 0, "retry_count": 0}
    for case in V1_CASES:
        agent = _agent()
        state = None
        for message in case.messages:
            state = agent.handle_message(case.case_id, "eval-user", message)
        assert state is not None
        metrics["task_success"] += int(state.status == case.expected_status)
        metrics["tool_success"] += int(any(result.success for result in state.tool_results))
        metrics["handoff"] += int(state.status is AgentStatus.HANDOFF)
        metrics["retry_count"] += state.retry_count
    return metrics
