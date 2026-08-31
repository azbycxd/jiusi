"""Run three independent live retests only for explicitly supplied first-pass failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from evals.harness import aggregate_results, evaluate_case
from evals.run import load_cases, run_live_case


def main() -> None:
    parser = argparse.ArgumentParser(description="Retest selected live Eval failures without changing first-pass results.")
    parser.add_argument("--case", action="append", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs != 3:
        raise SystemExit("V2-9B retests require exactly three independent runs")
    available = {case.case_id: case for case in load_cases()}
    missing = [case_id for case_id in args.case if case_id not in available]
    if missing:
        raise SystemExit(f"Unknown cases: {missing}")
    groups = []
    for case_id in args.case:
        case = available[case_id]
        results = [evaluate_case(case, run_live_case(case, run_token=f"retest-{index + 1}")) for index in range(args.runs)]
        groups.append({"case_id": case_id, "results": [item.model_dump(mode="json") for item in results], "aggregate": aggregate_results(results)})
    payload = {"mode": "live_retest", "groups": groups}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"groups": len(groups), "runs_per_case": args.runs, "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
