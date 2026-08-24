from __future__ import annotations

import time

from agent.response import answer_for_reason
from agent.router import route
from agent.state import AgentState, AgentStatus
from agent.termination import TerminationPolicy
from memory.session_memory import SessionMemory
from observability.trace import TraceRecorder
from tools.java_market_client import GetOrderDiagnosisTool
from tools.registry import ToolRegistry
from tools.schemas import ToolResult


class OrderDiagnosisOrchestrator:
    """Finite V1 control flow for exactly one order-diagnosis scenario."""

    def __init__(self, memory: SessionMemory | None = None, registry: ToolRegistry | None = None) -> None:
        self.memory = memory or SessionMemory()
        self.registry = registry or ToolRegistry([GetOrderDiagnosisTool()])

    def handle_message(self, session_id: str, authenticated_user_id: str, user_query: str) -> AgentState:
        state = self.memory.load_state(session_id)
        if state is None or state.authenticated_user_id != authenticated_user_id:
            state = AgentState(session_id=session_id, authenticated_user_id=authenticated_user_id)
        elif state.status in {AgentStatus.FINISHED, AgentStatus.FAILED, AgentStatus.HANDOFF}:
            state = AgentState(session_id=session_id, authenticated_user_id=authenticated_user_id)

        state.control.status = AgentStatus.RUNNING
        state.control.final_answer = None
        state.control.iteration_count += 1
        trace = TraceRecorder()
        route(state, user_query)
        trace.record(session_id=session_id, stage="ROUTED", action="route", iteration_count=state.iteration_count,
                     tool_call_count=state.tool_call_count)

        if TerminationPolicy.enforce(state):
            return self._save(state, trace)
        if state.intent.value != "ORDER_DIAGNOSIS":
            TerminationPolicy.handoff(state, "当前 V1 仅支持拼团订单诊断，已转人工客服处理。")
            return self._save(state, trace)
        if not state.out_trade_no:
            state.context.missing_fields = ["out_trade_no"]
            state.control.status = AgentStatus.WAITING_USER
            state.control.final_answer = "请提供需要查询的拼团订单号（outTradeNo）。"
            trace.record(session_id=session_id, stage="WAITING_SLOT", action="request_out_trade_no",
                         iteration_count=state.iteration_count, tool_call_count=state.tool_call_count)
            return self._save(state, trace)

        state.context.missing_fields = []
        return self._diagnose(state, trace)

    def _diagnose(self, state: AgentState, trace: TraceRecorder) -> AgentState:
        while state.control.retry_count <= state.control.max_retries:
            if TerminationPolicy.enforce(state):
                return self._save(state, trace)
            state.control.tool_call_count += 1
            started = time.perf_counter()
            try:
                result = self.registry.call("get_order_diagnosis", state)
            except Exception:
                result = ToolResult.infrastructure_failure(
                    "UNEXPECTED_TOOL_FAILURE", "订单诊断工具发生未预期错误", retryable=False, source="orchestrator"
                )
            state.context.tool_results.append(result)
            state.context.evidence.extend(item.model_dump() for item in result.evidence)
            trace.record(session_id=state.session_id, stage="TOOL_RESULT", action="get_order_diagnosis",
                         tool_name="get_order_diagnosis", tool_success=result.success, error_code=result.error_code,
                         started_at=started, iteration_count=state.iteration_count, tool_call_count=state.tool_call_count)

            if result.success:
                reason_code = str(result.data.get("reasonCode", "UNKNOWN_DIAGNOSIS"))
                state.context.diagnosis_code = reason_code
                answer = answer_for_reason(reason_code)
                if answer is None:
                    TerminationPolicy.handoff(state, "订单诊断结果需要人工客服进一步确认。")
                else:
                    state.control.status = AgentStatus.FINISHED
                    state.control.final_answer = answer
                return self._save(state, trace)

            if result.error_code == "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED":
                state.control.status = AgentStatus.FINISHED
                state.control.final_answer = "订单不存在，或当前账号无权查看该订单。"
                return self._save(state, trace)
            if result.retryable and state.control.retry_count < state.control.max_retries:
                state.control.retry_count += 1
                continue
            if result.retryable:
                TerminationPolicy.handoff(state, "订单服务暂时不可用且重试已达上限，已转人工客服处理。")
            else:
                state.control.status = AgentStatus.FAILED
                state.control.final_answer = "暂时无法完成订单诊断，请联系人工客服协助处理。"
            return self._save(state, trace)
        TerminationPolicy.handoff(state, "订单诊断重试已达上限，已转人工客服处理。")
        return self._save(state, trace)

    def _save(self, state: AgentState, trace: TraceRecorder | None = None) -> AgentState:
        self.memory.save_state(state.session_id, state)
        if trace:
            trace.record(
                session_id=state.session_id,
                stage=state.status.value,
                action="persist_state",
                iteration_count=state.iteration_count,
                tool_call_count=state.tool_call_count,
            )
        return state
