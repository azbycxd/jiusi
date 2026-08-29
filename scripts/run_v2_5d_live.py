"""Run the V2-5D real LLM/Java behavior evaluation without exposing secrets."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from argparse import ArgumentParser
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.orchestrator import OrderFactsOrchestrator
from decision.real_llm import RealLLMDecisionModel


class TraceCollector(logging.Handler):
    """Collect trace events in memory so the script prints only their safe summary."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        self.events.append({
            key: event.get(key)
            for key in (
                "stage", "action", "tool_name", "tool_success", "error_code", "duration_ms",
                "iteration_count", "tool_call_count", "retry_count", "model_call_count", "model_retry_count",
            )
        })


class RecordingRealDecisionModel:
    """Delegates to the real provider and records only parsed decision-safe telemetry."""

    def __init__(self) -> None:
        self._inner = RealLLMDecisionModel()
        self.decisions: list[dict[str, Any]] = []
        self.contexts = []
        self.telemetry: list[dict[str, Any]] = []

    @property
    def last_telemetry(self):
        return self._inner.last_telemetry

    def decide(self, context):
        self.contexts.append(context)
        raw = self._inner.decide(context)
        if isinstance(raw, dict):
            summary: dict[str, Any] = {"action": raw.get("action")}
            if raw.get("action") == "CALL_TOOL":
                arguments = raw.get("tool_arguments")
                summary.update({
                    "tool_name": raw.get("tool_name"),
                    "tool_arguments": arguments if isinstance(arguments, dict) else None,
                })
            elif raw.get("action") == "ANSWER":
                summary.update({
                    "final_answer": raw.get("final_answer"),
                    "used_evidence": raw.get("used_evidence"),
                })
            elif raw.get("action") == "HANDOFF":
                summary["missing_information"] = raw.get("missing_information")
            self.decisions.append(summary)
        telemetry = self._inner.last_telemetry
        if telemetry is not None:
            self.telemetry.append(asdict(telemetry))
        return raw


def _observation_summary(observation) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "tool_name": observation.tool_name,
        "evidence_paths": [item.kind for item in observation.evidence],
    }
    if observation.tool_name == "get_order_facts":
        references = observation.data.get("references")
        summary["activity_id"] = references.get("activity_id") if isinstance(references, dict) else None
    elif observation.tool_name == "get_joinable_team_facts":
        teams = observation.data.get("candidate_teams")
        summary["candidate_team_count"] = len(teams) if isinstance(teams, list) else None
        summary["statistics"] = observation.data.get("statistics")
    return summary


def run_case(name: str, user_query: str) -> dict[str, Any]:
    trace_logger = logging.getLogger("group_buy_agent.trace")
    original_handlers = list(trace_logger.handlers)
    collector = TraceCollector()
    trace_logger.handlers = [collector]
    model = RecordingRealDecisionModel()
    agent = OrderFactsOrchestrator(decision_model=model)
    try:
        # The trusted identity is passed only to the Agent runtime and is never emitted.
        state = agent.handle_message(f"v25d-{name}-{uuid.uuid4().hex}", "xfg05", user_query)
        return {
            "name": name,
            "status": state.status.value,
            "final_answer": state.final_answer,
            "decisions": model.decisions,
            "contexts": [
                {
                    "observation_tools": [item.tool_name for item in context.observations],
                    "available_tools": [item.name for item in context.available_tools],
                    "evidence_paths": [item["kind"] for item in context.evidence],
                }
                for context in model.contexts
            ],
            "observations": [_observation_summary(item) for item in state.observations],
            "counts": {
                "model_call_count": state.model_call_count,
                "model_retry_count": state.model_retry_count,
                "tool_call_count": state.tool_call_count,
                "retry_count": state.retry_count,
                "observation_count": len(state.observations),
            },
            "telemetry": model.telemetry,
            "trace": collector.events,
        }
    finally:
        trace_logger.handlers = original_handlers


def main() -> None:
    core_question = "为什么我的订单 644398015396 还没有拼团成功？如果这个团现在不能继续了，还有别的团可以参加吗？"
    all_cases = [
        *((f"core-{index}", core_question) for index in range(1, 4)),
        ("direct-activity", "活动 100123 现在还有其它可以加入的团吗？"),
        ("single-order", "订单 644398015396 当前是什么状态？"),
        ("refund", "我的退款什么时候到账？"),
        ("capability", "你现在能帮我查什么？"),
    ]
    parser = ArgumentParser()
    parser.add_argument("--case", choices=[name for name, _ in all_cases])
    selected = parser.parse_args().case
    requested_cases = [item for item in all_cases if item[0] == selected] if selected else all_cases
    for name, user_query in requested_cases:
        print(json.dumps(run_case(name, user_query), ensure_ascii=False, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
