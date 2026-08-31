from __future__ import annotations

import argparse
import json
import logging
import uuid
from pathlib import Path

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus
from decision.real_llm import RealLLMDecisionModel
from evals.contracts import EvalCase, EvalExecution, ExpectedFinalAction, ToolCallRecord
from evals.deterministic import run_deterministic_case
from evals.harness import aggregate_results, evaluate_case


DEFAULT_CASES_PATH = Path(__file__).with_name("cases") / "v2_agent_eval_cases.json"
REAL_BEHAVIOR_CATEGORIES = frozenset({
    "rule_knowledge", "realtime_facts", "multi_source", "dynamic_chaining",
    "handoff", "injection", "unrelated", "capability",
})


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Eval cases payload is invalid")
    cases = [EvalCase.model_validate(item) for item in payload["cases"]]
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Eval case_id values must be unique")
    return cases


class _LiveTraceCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        if isinstance(event.get("error_code"), str):
            self.errors.append(event["error_code"])


def _tool_records(state) -> list[ToolCallRecord]:
    records: list[ToolCallRecord] = []
    for signature in state.context.tool_call_history:
        name, raw = signature.split(":", 1)
        records.append(ToolCallRecord(tool_name=name, arguments=json.loads(raw)))
    return records


def run_live_case(case: EvalCase, *, run_token: str | None = None) -> EvalExecution:
    """Run an explicitly selected live case; trusted test identity never enters output."""
    logger = logging.getLogger("group_buy_agent.trace")
    original_handlers = list(logger.handlers)
    collector = _LiveTraceCollector()
    logger.handlers = [collector]
    try:
        state = OrderFactsOrchestrator(decision_model=RealLLMDecisionModel()).handle_message(
            f"live-eval-{case.case_id}-{run_token or uuid.uuid4().hex}", "xfg05", case.user_query
        )
    finally:
        logger.handlers = original_handlers
    final_action = ExpectedFinalAction.ANSWER if state.status is AgentStatus.FINISHED else ExpectedFinalAction.HANDOFF
    decision = state.context.model_decision or {}
    used_evidence = decision.get("used_evidence", []) if decision.get("action") == "ANSWER" else []
    errors = collector.errors
    infrastructure_error = "MODEL_TIMEOUT" if state.status is AgentStatus.HANDOFF and errors and not decision else None
    return EvalExecution(
        final_action=final_action, tool_calls=_tool_records(state),
        observations=[item.model_dump(mode="json") for item in state.observations],
        used_evidence=used_evidence if isinstance(used_evidence, list) else [],
        final_answer=state.final_answer or "", model_call_count=state.model_call_count,
        model_retry_count=state.model_retry_count, retry_count=state.retry_count,
        guard_errors=errors, infrastructure_error=infrastructure_error,
    )


def run_cases(cases: list[EvalCase], *, mode: str) -> dict:
    results = [evaluate_case(case, run_deterministic_case(case) if mode == "deterministic" else run_live_case(case)) for case in cases]
    return {"mode": mode, "results": [item.model_dump(mode="json") for item in results], "aggregate": aggregate_results(results)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic or small selected live Agent evaluations.")
    parser.add_argument("--mode", choices=("deterministic", "live"), required=True)
    parser.add_argument("--case")
    parser.add_argument("--category")
    parser.add_argument("--all-behavior", action="store_true", help="Run all RealLLM behavior categories once each.")
    parser.add_argument("--output", type=Path, help="Write the safe structured result JSON to this path.")
    args = parser.parse_args()
    cases = load_cases()
    if args.case:
        cases = [case for case in cases if case.case_id == args.case]
    if args.category:
        cases = [case for case in cases if case.category == args.category]
    if args.all_behavior:
        if args.mode != "live":
            raise SystemExit("--all-behavior requires --mode live")
        if args.case or args.category:
            raise SystemExit("--all-behavior cannot be combined with --case or --category")
        cases = [case for case in cases if case.category in REAL_BEHAVIOR_CATEGORIES]
    if args.mode == "live" and not args.case and not args.category and not args.all_behavior:
        cases = [case for case in cases if case.requires_live_provider]
    if not cases:
        raise SystemExit("No matching eval cases")
    output = run_cases(cases, mode=args.mode)
    encoded = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(json.dumps({"mode": args.mode, "aggregate": output["aggregate"], "output": str(args.output) if args.output else None}, ensure_ascii=False))


if __name__ == "__main__":
    main()
