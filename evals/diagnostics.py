"""Safe, live-only diagnostics for explicitly selected evaluation cases.

This module intentionally wraps the existing DecisionModel and Orchestrator rather
than changing either production boundary.  It captures only structured decisions,
observation evidence paths, and safe trace fields needed to diagnose an Eval Case.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from agent.orchestrator import OrderFactsOrchestrator
from decision.real_llm import RealLLMDecisionModel
from decision.schemas import DecisionContext
from evals.run import load_cases


def _summary_of_raw_decision(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"payload_type": type(raw).__name__}
    summary: dict[str, Any] = {"action": raw.get("action")}
    if raw.get("action") == "CALL_TOOL":
        summary["tool_name"] = raw.get("tool_name")
        arguments = raw.get("tool_arguments")
        summary["tool_arguments"] = arguments if isinstance(arguments, dict) else None
    elif raw.get("action") == "ANSWER":
        summary["final_answer"] = raw.get("final_answer") if isinstance(raw.get("final_answer"), str) else None
        summary["used_evidence"] = raw.get("used_evidence") if isinstance(raw.get("used_evidence"), list) else None
    elif raw.get("action") == "HANDOFF":
        summary["missing_information"] = raw.get("missing_information") if isinstance(raw.get("missing_information"), list) else None
    return summary


def _summary_of_observations(observation_items: list[Any]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for observation in observation_items:
        data = observation.data
        summary: dict[str, Any] = {
            "tool_name": observation.tool_name,
            "evidence_paths": [item.kind for item in observation.evidence],
        }
        if observation.tool_name == "get_joinable_team_facts":
            candidates = data.get("candidate_teams")
            if isinstance(candidates, list):
                summary["candidate_teams_empty"] = not candidates
                summary["candidate_team_count"] = len(candidates)
        if observation.tool_name == "search_group_buy_rules":
            results = data.get("results")
            if isinstance(results, list):
                summary["knowledge_ids"] = [
                    item.get("knowledge_id") for item in results
                    if isinstance(item, dict) and isinstance(item.get("knowledge_id"), str)
                ]
        observations.append(summary)
    return observations


def _summary_of_context(context: DecisionContext) -> dict[str, Any]:
    return {
        "observation_summaries": _summary_of_observations(context.observations),
        "evidence_paths": [item["kind"] for item in context.evidence],
    }


class RecordingDecisionModel:
    """Observes safe model I/O metadata without storing prompts or provider responses."""

    def __init__(self, delegate: RealLLMDecisionModel) -> None:
        self._delegate = delegate
        self.decisions: list[dict[str, Any]] = []

    @property
    def last_telemetry(self):
        return self._delegate.last_telemetry

    def decide(self, context: DecisionContext) -> object:
        item: dict[str, Any] = {"context": _summary_of_context(context)}
        try:
            raw = self._delegate.decide(context)
        except Exception as error:
            item["model_error_type"] = type(error).__name__
            self.decisions.append(item)
            raise
        item["raw_decision_summary"] = _summary_of_raw_decision(raw)
        self.decisions.append(item)
        return raw


class _SafeTraceCollector(logging.Handler):
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
            for key in ("stage", "action", "tool_name", "tool_success", "error_code", "tool_call_count", "retry_count", "model_call_count", "model_retry_count")
        })


def _handoff_trigger(state, trace_events: list[dict[str, Any]]) -> str | None:
    decision = state.context.model_decision or {}
    if decision.get("action") == "HANDOFF":
        return "MODEL_DECISION_HANDOFF"
    validation_errors = [event.get("error_code") for event in trace_events if event.get("stage") == "MODEL_VALIDATION_ERROR"]
    if validation_errors:
        return f"MODEL_VALIDATION_ERROR:{validation_errors[-1]}"
    if any(event.get("error_code") == "TOOL_REPEAT_LIMIT" for event in trace_events):
        return "TOOL_REPEAT_LIMIT"
    return "TERMINATION_OR_TOOL_FAILURE"


def run_live_diagnosis(case_id: str, *, runs: int = 1, user_query: str | None = None) -> dict[str, Any]:
    cases = {case.case_id: case for case in load_cases()}
    if case_id not in cases:
        raise ValueError(f"Unknown eval case: {case_id}")
    case = cases[case_id]
    query = user_query.strip() if isinstance(user_query, str) and user_query.strip() else case.user_query
    results: list[dict[str, Any]] = []
    logger = logging.getLogger("group_buy_agent.trace")
    for index in range(runs):
        original_handlers = list(logger.handlers)
        collector = _SafeTraceCollector()
        logger.handlers = [collector]
        model = RecordingDecisionModel(RealLLMDecisionModel())
        try:
            state = OrderFactsOrchestrator(decision_model=model).handle_message(
                f"diagnostic-{case.case_id}-{index + 1}", "xfg05", query
            )
        finally:
            logger.handlers = original_handlers
        final_decision = state.context.model_decision or {}
        results.append({
            "run": index + 1,
            "model_decisions": model.decisions,
            "tool_sequence": [item.split(":", 1)[0] for item in state.context.tool_call_history],
            "observation_summaries": _summary_of_observations(state.observations),
            "final_action": final_decision.get("action") or state.status.value,
            "final_answer": state.final_answer or "",
            "used_evidence": final_decision.get("used_evidence", []) if final_decision.get("action") == "ANSWER" else [],
            "handoff_trigger": _handoff_trigger(state, collector.events) if state.status.value == "HANDOFF" else None,
            "trace": collector.events,
            "model_call_count": state.model_call_count,
            "model_retry_count": state.model_retry_count,
            "termination_status": state.status.value,
        })
    return {"case_id": case.case_id, "runs": results}


def compact_diagnosis(payload: dict[str, Any]) -> dict[str, Any]:
    """Return repeat-run telemetry without retaining answers, contexts, or raw decisions."""
    return {
        "case_id": payload["case_id"],
        "runs": [
            {
                "run": item["run"],
                "final_action": item["final_action"],
                "tool_sequence": item["tool_sequence"],
                "used_evidence": item["used_evidence"],
                "handoff_trigger": item["handoff_trigger"],
                "model_call_count": item["model_call_count"],
                "model_retry_count": item["model_retry_count"],
                "termination_status": item["termination_status"],
                "error_codes": [event["error_code"] for event in item["trace"] if event["error_code"]],
            }
            for item in payload["runs"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run safe live diagnostics for one eval case.")
    parser.add_argument("--case", required=True)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--query", help="Explicit local diagnostic query; it is never persisted by this module.")
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    payload = run_live_diagnosis(args.case, runs=args.runs, user_query=args.query)
    print(json.dumps(compact_diagnosis(payload) if args.compact else payload, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    main()
