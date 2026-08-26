"""Send one acceptance request to an already running local Agent HTTP server."""

from __future__ import annotations

import argparse
import json

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--message", required=True)
    args = parser.parse_args()
    response = httpx.post(
        f"{args.base_url.rstrip('/')}/v1/chat",
        json={"session_id": args.session_id, "message": args.message},
        headers={"X-Authenticated-User-Id": args.identity},
        timeout=180.0,
        trust_env=False,
    )
    print(json.dumps({"status_code": response.status_code, "body": response.json()}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
