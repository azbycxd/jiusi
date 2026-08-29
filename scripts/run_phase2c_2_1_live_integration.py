"""One-shot, read-only live validation for the configured LLM and Java facts API."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from agent.orchestrator import OrderFactsOrchestrator
from decision.normalization import normalize_agent_decision_payload
from decision.real_llm import RealLLMConfig, RealLLMDecisionModel
from decision.schemas import DecisionContext


class SafeTraceCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        # TraceRecorder already produces a safe allowlisted event. Keep only
        # the fields needed by the live acceptance report.
        self.events.append(
            {
                key: event.get(key)
                for key in (
                    "stage", "action", "tool_name", "tool_success", "error_code", "duration_ms",
                    "tool_call_count", "retry_count", "model_call_count", "model_retry_count", "model",
                    "input_tokens", "output_tokens", "total_tokens",
                )
            }
        )


class RecordingRealDecisionModel:
    """Observes parsed model proposals while delegating every call to the real adapter."""

    def __init__(self, delegate: RealLLMDecisionModel) -> None:
        self._delegate = delegate
        self.decisions: list[dict[str, Any]] = []

    @property
    def last_telemetry(self):
        return self._delegate.last_telemetry

    def decide(self, context: DecisionContext) -> object:
        decision = self._delegate.decide(context)
        if isinstance(decision, dict):
            normalized = normalize_agent_decision_payload(decision)
            fields = (
                "action", "tool_name", "tool_arguments", "final_answer", "used_evidence", "missing_information"
            )
            self.decisions.append(
                {
                    "normalization_applied": normalized != decision,
                    "raw": {key: decision.get(key) for key in fields},
                    "normalized": {key: normalized.get(key) for key in fields},
                }
            )
        else:
            self.decisions.append({"response_type": type(decision).__name__})
        return decision


def run_case(session_id: str, user_query: str, trace: SafeTraceCapture) -> dict[str, Any]:
    adapter = RealLLMDecisionModel(RealLLMConfig.from_environment())
    recorder = RecordingRealDecisionModel(adapter)
    agent = OrderFactsOrchestrator(decision_model=recorder)
    event_start = len(trace.events)
    state = agent.handle_message(session_id, "xfg05", user_query)
    return {
        "status": state.status.value,
        "final_answer": state.final_answer,
        "tool_call_count": state.tool_call_count,
        "retry_count": state.retry_count,
        "model_call_count": state.model_call_count,
        "model_retry_count": state.model_retry_count,
        "decisions": recorder.decisions,
        "tool_call_history": state.context.tool_call_history,
        "observations": [item.model_dump(mode="json") for item in state.context.observations],
        "tool_results": [
            {"success": result.success, "error_code": result.error_code, "source": result.source}
            for result in state.context.tool_results
        ],
        "trace": trace.events[event_start:],
    }


def main() -> int:
    trace = SafeTraceCapture()
    logger = logging.getLogger("group_buy_agent.trace")
    logger.addHandler(trace)
    logger.setLevel(logging.INFO)
    try:
        result = {
            "provider_type": "OpenAI-compatible relay",
            "scenario_a": run_case("phase2c-live-a", "你能帮我做什么？", trace),
            "scenario_b": run_case(
                "phase2c-live-b", "为什么我的订单 644398015396 还没有拼团成功？", trace
            ),
            "scenario_c": run_case("phase2c-live-c", "我的退款什么时候到账？", trace),
        }
    finally:
        logger.removeHandler(trace)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
