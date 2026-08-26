from __future__ import annotations

import json
import time
from dataclasses import replace

from agent.router import RoutingResult, route
from agent.state import AgentState, AgentStatus
from agent.termination import TerminationPolicy
from decision.model import DecisionModel
from decision.schemas import AgentAction
from decision.stage import DecisionStage, DecisionStageResult
from memory.session_memory import SessionMemory
from observability.trace import TraceRecorder
from tools.errors import to_tool_result
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import ToolResult


class OrderFactsOrchestrator:
    """Controlled agent loop. A model proposes actions; the harness owns all execution."""

    def __init__(
        self,
        memory: SessionMemory | None = None,
        registry: ToolRegistry | None = None,
        decision_model: DecisionModel | None = None,
        *,
        compatibility_mode: bool = False,
    ) -> None:
        if decision_model is None and not compatibility_mode:
            raise ValueError(
                "A DecisionModel is required for the Agent Loop; set compatibility_mode=True "
                "only for the temporary Phase 2B facts-retrieval flow."
            )
        self.memory = memory or SessionMemory()
        self.registry = registry or ToolRegistry([OrderFactsTool()])
        self._compatibility_mode = compatibility_mode
        self._decision_stage = DecisionStage(decision_model, self.registry.available_tools) if decision_model else None

    def handle_message(self, session_id: str, authenticated_user_id: str, user_query: str) -> AgentState:
        state = self.memory.load_state(session_id)
        if (
            state is None
            or state.authenticated_user_id != authenticated_user_id
            or state.status in {AgentStatus.FINISHED, AgentStatus.FAILED, AgentStatus.HANDOFF}
        ):
            state = AgentState(session_id=session_id, authenticated_user_id=authenticated_user_id)

        state.control.status = AgentStatus.RUNNING
        state.control.needs_human = False
        state.control.final_answer = None
        state.control.iteration_count += 1
        trace = TraceRecorder()
        routing = route(user_query, state.intent)
        self._apply_routing_result(state, routing)
        self._trace(trace, state, stage="ROUTED", action="route")

        if TerminationPolicy.enforce(state):
            return self._save(state, trace)
        if self._decision_stage:
            return self._run_agent_loop(state, trace)
        # This branch is opt-in only; it keeps the pre-LLM Phase 2B HTTP harness runnable.
        return self._run_facts_compatibility_flow(state, routing, trace)

    def _run_facts_compatibility_flow(
        self, state: AgentState, routing: RoutingResult, trace: TraceRecorder
    ) -> AgentState:
        """Explicit compatibility path when no DecisionModel has been configured."""
        if state.intent.value != "ORDER_FACTS":
            TerminationPolicy.handoff(state, "当前阶段仅支持拼团订单事实查询，已转人工客服处理。")
            return self._save(state, trace)
        if routing.has_out_trade_no_candidate and not routing.out_trade_no.is_valid:
            state.context.missing_fields = ["out_trade_no"]
            state.control.status = AgentStatus.WAITING_USER
            state.control.final_answer = "订单号格式无效，请提供有效的拼团订单号。"
            return self._save(state, trace)
        if not state.out_trade_no:
            state.context.missing_fields = ["out_trade_no"]
            state.control.status = AgentStatus.WAITING_USER
            state.control.final_answer = "请提供需要查询的拼团订单号（outTradeNo）。"
            self._trace(trace, state, stage="WAITING_SLOT", action="request_out_trade_no")
            return self._save(state, trace)
        state.context.missing_fields = []
        if self._execute_tool(state, trace, "get_order_facts"):
            state.control.status = AgentStatus.FINISHED
            state.control.final_answer = "FACTS_RETRIEVED"
        return self._save(state, trace)

    def _run_agent_loop(self, state: AgentState, trace: TraceRecorder) -> AgentState:
        """Finite Decision → Action → Observation loop; no Tool is preselected."""
        for _ in range(state.control.max_iterations):
            if TerminationPolicy.enforce(state):
                return self._save(state, trace)
            decision_result = self._ask_model(state, trace)
            if decision_result.decision is None:
                TerminationPolicy.handoff(state, "模型决策结果无效，已转人工客服处理。")
                return self._save(state, trace)
            decision = decision_result.decision
            state.context.model_decision = decision.model_dump(mode="json")
            self._trace(
                trace, state, stage="MODEL_DECISION", action=decision.action.value,
                started_at=decision_result.started_at, telemetry=decision_result.telemetry,
            )

            if decision.action is AgentAction.ANSWER:
                state.control.status = AgentStatus.FINISHED
                state.control.final_answer = decision.final_answer
                return self._save(state, trace)
            if decision.action is AgentAction.HANDOFF:
                TerminationPolicy.handoff(state, "模型建议转人工客服处理。")
                return self._save(state, trace)

            arguments = self._validate_tool_action(state, trace, decision.tool_name, decision.tool_arguments)
            if arguments is None:
                TerminationPolicy.handoff(state, "模型请求的工具或参数不符合安全策略，已转人工客服处理。")
                return self._save(state, trace)
            signature = f"{decision.tool_name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=True)}"
            if signature in state.context.tool_call_history:
                self._trace(
                    trace, state, stage="MODEL_VALIDATION_ERROR", action="duplicate_tool_call",
                    error_code="DUPLICATE_TOOL_CALL",
                )
                TerminationPolicy.handoff(state, "重复工具调用不会提供新事实，已转人工客服处理。")
                return self._save(state, trace)
            if TerminationPolicy.enforce(state):
                return self._save(state, trace)

            state.context.out_trade_no = arguments["outTradeNo"]
            state.context.missing_fields = []
            state.context.tool_call_history.append(signature)
            if not self._execute_tool(state, trace, decision.tool_name):
                return self._save(state, trace)
            # A completed observation starts the next Decision/Reason turn.
            state.control.iteration_count += 1

        TerminationPolicy.handoff(state, "Agent 迭代次数已达上限，已转人工客服处理。")
        return self._save(state, trace)

    def _ask_model(self, state: AgentState, trace: TraceRecorder) -> DecisionStageResult:
        assert self._decision_stage is not None
        context = self._decision_stage.build_context(
            user_query=state.user_query,
            facts=state.order_facts or {},
            evidence=state.evidence,
        )
        for _ in range(state.control.max_model_retries + 1):
            state.control.model_call_count += 1
            started = time.perf_counter()
            result = replace(self._decision_stage.decide(context), started_at=started)
            if result.error_code is None:
                return result
            self._trace(
                trace,
                state,
                stage="MODEL_VALIDATION_ERROR",
                action="validate_decision",
                error_code=result.error_code,
                started_at=started,
                telemetry=result.telemetry,
            )
            remaining = state.control.max_model_retries - state.control.model_retry_count
            if result.retryable and remaining > 0:
                state.control.model_retry_count += 1
                continue
            return result
        return DecisionStageResult(error_code="MODEL_RETRY_LIMIT")

    def _validate_tool_action(
        self, state: AgentState, trace: TraceRecorder, tool_name: str | None, arguments: object
    ) -> dict[str, str] | None:
        if not tool_name or tool_name not in state.capability.allowed_tools:
            self._trace(trace, state, stage="MODEL_VALIDATION_ERROR", action="validate_capability", error_code="MODEL_TOOL_NOT_ALLOWED")
            return None
        if tool_name not in self.registry.allowed_names:
            self._trace(trace, state, stage="MODEL_VALIDATION_ERROR", action="validate_registry", error_code="MODEL_TOOL_NOT_ALLOWED")
            return None
        normalized = self.registry.validate_arguments(tool_name, arguments)
        if normalized is None:
            self._trace(trace, state, stage="MODEL_VALIDATION_ERROR", action="validate_tool_arguments", error_code="MODEL_TOOL_ARGUMENTS_INVALID")
            return None
        return normalized

    def _execute_tool(self, state: AgentState, trace: TraceRecorder, tool_name: str) -> bool:
        """Run one harness-approved Tool with the existing finite Tool retry policy."""
        for _ in range(state.control.max_retries + 1):
            if TerminationPolicy.enforce(state):
                return False
            state.control.tool_call_count += 1
            started = time.perf_counter()
            self._trace(trace, state, stage="TOOL_CALL", action=tool_name, tool_name=tool_name)
            try:
                result = self.registry.call(tool_name, state)
            except Exception as error:
                result = to_tool_result(error, source="orchestrator")
            self._apply_tool_result(state, result)
            self._trace(
                trace,
                state,
                stage="TOOL_RESULT",
                action=tool_name,
                tool_name=tool_name,
                tool_success=result.success,
                error_code=result.error_code,
                started_at=started,
            )
            if result.success:
                return True
            if result.error_code == "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED":
                state.control.status = AgentStatus.FINISHED
                state.control.final_answer = "订单不存在，或当前账号无权查看该订单。"
                return False
            remaining_retries = state.control.max_retries - state.control.retry_count
            if result.retryable and remaining_retries > 0:
                state.control.retry_count += 1
                continue
            if result.retryable:
                TerminationPolicy.handoff(state, "订单事实服务暂时不可用且重试已达上限，已转人工客服处理。")
            else:
                state.control.status = AgentStatus.FAILED
                state.control.final_answer = "暂时无法获取订单事实，请联系人工客服协助处理。"
            return False
        return False

    @staticmethod
    def _apply_routing_result(state: AgentState, routing: RoutingResult) -> None:
        state.context.user_query = routing.normalized_query
        state.context.intent = routing.intent
        if routing.out_trade_no.is_valid:
            state.context.out_trade_no = routing.out_trade_no.value
        elif routing.has_out_trade_no_candidate:
            state.context.out_trade_no = None

    @staticmethod
    def _apply_tool_result(state: AgentState, result: ToolResult) -> None:
        state.context.tool_results.append(result)
        state.context.evidence.extend(item.model_dump() for item in result.evidence)
        if not result.success:
            return
        facts = result.data.get("facts")
        if not isinstance(facts, dict):
            return
        state.context.order_facts = facts
        references = facts.get("references")
        if isinstance(references, dict):
            state.context.team_id = str(references["team_id"]) if references.get("team_id") is not None else None
            state.context.activity_id = str(references["activity_id"]) if references.get("activity_id") is not None else None

    @staticmethod
    def _trace(
        trace: TraceRecorder,
        state: AgentState,
        *,
        stage: str,
        action: str,
        tool_name: str | None = None,
        tool_success: bool | None = None,
        error_code: str | None = None,
        started_at: float | None = None,
        telemetry=None,
    ) -> None:
        trace.record(
            session_id=state.session_id,
            stage=stage,
            action=action,
            tool_name=tool_name,
            tool_success=tool_success,
            error_code=error_code,
            started_at=started_at,
            iteration_count=state.iteration_count,
            tool_call_count=state.tool_call_count,
            retry_count=state.retry_count,
            model_call_count=state.model_call_count,
            model_retry_count=state.model_retry_count,
            model=telemetry.model if telemetry else None,
            input_tokens=telemetry.input_tokens if telemetry else None,
            output_tokens=telemetry.output_tokens if telemetry else None,
            total_tokens=telemetry.total_tokens if telemetry else None,
        )

    def _save(self, state: AgentState, trace: TraceRecorder | None = None) -> AgentState:
        self.memory.save_state(state.session_id, state)
        if trace:
            self._trace(trace, state, stage=state.status.value, action="persist_state")
        return state
