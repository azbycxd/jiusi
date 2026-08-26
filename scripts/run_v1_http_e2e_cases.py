"""Send live V1 acceptance requests through the public FastAPI HTTP endpoint only."""

from __future__ import annotations

import json

import httpx


BASE_URL = "http://127.0.0.1:8010"


def request(client: httpx.Client, name: str, session_id: str, identity: str, message: str) -> dict:
    response = client.post(
        f"{BASE_URL}/v1/chat",
        json={"session_id": session_id, "message": message},
        headers={"X-Authenticated-User-Id": identity},
    )
    return {"case": name, "http_status": response.status_code, "response": response.json()}


def main() -> int:
    with httpx.Client(timeout=180.0, trust_env=False) as client:
        results = [
            request(client, "no_tool", "v1-http-a", "xfg05", "你能帮我做什么？"),
            request(client, "order_facts", "v1-http-b", "xfg05", "为什么我的订单 644398015396 还没有拼团成功？"),
            request(client, "unsupported", "v1-http-c", "xfg05", "我的退款什么时候到账？"),
            request(client, "invalid_order", "v1-http-invalid", "xfg05", "查询订单 @@@"),
            request(client, "unauthorized", "v1-http-unauthorized", "xfg03", "为什么我的订单 644398015396 还没有拼团成功？"),
        ]
    print(json.dumps(results, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
