"""Local Phase 1 acceptance evidence runner; no network or external service calls."""

from __future__ import annotations

import inspect
import json
import logging

from agent.orchestrator import OrderDiagnosisOrchestrator
from agent.state import AgentState
from tools.java_market_client import GetOrderDiagnosisTool, JavaMarketClient
from tools.schemas import ToolResult


def summary(state: AgentState) -> dict[str, object]:
    return {
        "status": state.status.value,
        "intent": state.intent.value,
        "out_trade_no": state.out_trade_no,
        "missing_fields": state.missing_fields,
        "retry_count": state.retry_count,
        "iteration_count": state.iteration_count,
        "tool_call_count": state.tool_call_count,
        "diagnosis_code": state.diagnosis_code,
        "needs_human": state.needs_human,
        "answer": state.final_answer,
        "tool_results": [result.model_dump() for result in state.tool_results],
    }


def emit(label: str, value: object) -> None:
    print(f"{label}={json.dumps(value, ensure_ascii=True)}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="TRACE %(message)s")
    agent = OrderDiagnosisOrchestrator()

    success = agent.handle_message(
        "accept-success", "trusted-accept-user", "我的订单 202608240001 为什么还没有拼团成功？"
    )
    emit("SUCCESS", summary(success))
    logging.getLogger("group_buy_agent.trace").setLevel(logging.WARNING)

    first = agent.handle_message("accept-resume", "trusted-accept-user", "我的拼团为什么还没成功？")
    second = agent.handle_message("accept-resume", "trusted-accept-user", "202608240001")
    emit("SESSION_RESUME", {"first": summary(first), "second": summary(second)})

    failures: dict[str, dict[str, object]] = {}
    for order_no in ("202608240005", "202608240006", "202608240007", "202608240004"):
        failures[order_no] = summary(
            agent.handle_message(f"accept-{order_no}", "trusted-accept-user", f"查询拼团订单 {order_no}")
        )
    emit("FAILURE_CASES", failures)

    iteration_state = AgentState(session_id="limit-iteration", authenticated_user_id="trusted-accept-user")
    iteration_state.control.max_iterations = 1
    agent.memory.save_state(iteration_state.session_id, iteration_state)
    tool_limit_state = AgentState(session_id="limit-tools", authenticated_user_id="trusted-accept-user")
    tool_limit_state.control.max_tool_calls = 1
    tool_limit_state.control.max_retries = 5
    agent.memory.save_state(tool_limit_state.session_id, tool_limit_state)
    emit(
        "TERMINATION_LIMITS",
        {
            "max_iterations": summary(agent.handle_message("limit-iteration", "trusted-accept-user", "查询拼团订单 202608240001")),
            "max_tool_calls": summary(agent.handle_message("limit-tools", "trusted-accept-user", "查询拼团订单 202608240005")),
        },
    )
    emit(
        "BOUNDARIES",
        {
            "registry_allowlist": list(agent.registry.allowed_names),
            "tool_run_signature": str(inspect.signature(GetOrderDiagnosisTool.run)),
            "java_facade_signature": str(inspect.signature(JavaMarketClient.get_order_diagnosis)),
            "tool_result_fields": list(ToolResult.model_fields),
        },
    )


if __name__ == "__main__":
    main()
