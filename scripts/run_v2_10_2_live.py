"""Run the V2-10.2 real HTTP audit without recording secrets or response text."""

from __future__ import annotations

import json
from pathlib import Path

import httpx


BASE_URL = "http://127.0.0.1:8011"
OUT = Path("reports/evals/V2-10.2_live_http.json")
_SENSITIVE_MARKERS = ("traceback", "exception", "sql", "mapper", "stack")


def _safe_result(case: str, response: httpx.Response) -> dict[str, object]:
    try:
        body = response.json()
    except ValueError:
        body = {}
    text = response.text.lower()
    return {
        "case": case,
        "http_status": response.status_code,
        "status": body.get("status") if isinstance(body, dict) else None,
        "needs_human": body.get("needs_human") if isinstance(body, dict) else None,
        "has_answer": bool(body.get("answer")) if isinstance(body, dict) else False,
        "missing_field_count": len(body.get("missing_fields", [])) if isinstance(body, dict) else None,
        "public_response_has_internal_leak": any(marker in text for marker in _SENSITIVE_MARKERS),
    }


def _post(client: httpx.Client, case: str, session_id: str, message: str, identity: str) -> dict[str, object]:
    response = client.post(
        f"{BASE_URL}/v1/chat",
        json={"session_id": session_id, "message": message},
        headers={"X-Authenticated-User-Id": identity},
    )
    return _safe_result(case, response)


def main() -> None:
    # Identity labels are intentionally not persisted; only the two separate headers are used.
    results: list[dict[str, object]] = []
    with httpx.Client(timeout=180.0, trust_env=False) as client:
        results.append(_post(client, "session_a_order", "v2102-session-a", "订单644398015396现在什么状态？", "xfg05"))
        results.append(_post(client, "session_a_follow_up", "v2102-session-a", "那这个团还有其它团能参加吗？", "xfg05"))
        results.append(_post(client, "session_b_follow_up", "v2102-session-b", "那这个团还有其它团能参加吗？", "xfg05"))

        results.append(_post(client, "identity_a_seed", "v2102-cross-identity", "订单644398015396现在什么状态？", "xfg05"))
        results.append(_post(client, "identity_b_follow_up", "v2102-cross-identity", "那这个团还有其它团能参加吗？", "xfg03"))

        unknown_order = "v2-10-2-known-absent-order-20260831"
        results.append(_post(
            client,
            "unknown_order",
            "v2102-unknown-order",
            f"订单 {unknown_order} 现在是什么状态？",
            "xfg05",
        ))

        facts_rag_message = "为什么订单644398015396还没成团，成团规则是什么？"
        for number in range(1, 4):
            results.append(_post(client, f"facts_rag_{number}", f"v2102-facts-rag-{number}", facts_rag_message, "xfg05"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps([{"case": item["case"], "http_status": item["http_status"], "status": item["status"]} for item in results], ensure_ascii=False))


if __name__ == "__main__":
    main()
