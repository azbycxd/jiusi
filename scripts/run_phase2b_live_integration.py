"""Run the Phase 2B live checks through the complete Agent orchestration path.

All test identities, order numbers and the intentionally bad connection URL are
provided as command-line inputs. Business code contains none of these values.
"""

from __future__ import annotations

import argparse
import json
import logging
import socket

from agent.orchestrator import OrderFactsOrchestrator
from tools.java_market_client import JavaMarketClient, JavaMarketClientConfig, OrderFactsTool
from tools.registry import ToolRegistry


class TraceCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.events: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.events.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            pass


def summarise(state) -> dict:
    return {
        "status": state.status.value,
        "answer": state.final_answer,
        "tool_call_count": state.tool_call_count,
        "retry_count": state.retry_count,
        "diagnosis_code": state.diagnosis_code,
        "observations": [item.model_dump(mode="json") for item in state.observations],
        "tool_results": [result.model_dump() for result in state.tool_results],
    }


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorized-user", required=True)
    parser.add_argument("--unauthorized-user", required=True)
    parser.add_argument("--out-trade-no", required=True)
    parser.add_argument(
        "--connection-base-url",
        required=True,
        help="Test-only error URL, or reserved-closed-port for a temporary non-listening loopback port.",
    )
    return parser.parse_args()


def main() -> int:
    args = arguments()
    capture = TraceCapture()
    logger = logging.getLogger("group_buy_agent.trace")
    logger.addHandler(capture)
    logger.setLevel(logging.INFO)
    try:
        positive_agent = OrderFactsOrchestrator(compatibility_mode=True)
        positive = positive_agent.handle_message(
            "phase2b-live-positive", args.authorized_user, f"查询订单 {args.out_trade_no}"
        )
        unauthorized_agent = OrderFactsOrchestrator(compatibility_mode=True)
        unauthorized = unauthorized_agent.handle_message(
            "phase2b-live-unauthorized", args.unauthorized_user, f"查询订单 {args.out_trade_no}"
        )
        no_auth_agent = OrderFactsOrchestrator(compatibility_mode=True)
        no_auth = no_auth_agent.handle_message("phase2b-live-no-auth", "", f"查询订单 {args.out_trade_no}")

        reserved_socket = None
        connection_base_url = args.connection_base_url
        if connection_base_url == "reserved-closed-port":
            # Keep a bound but non-listening socket open: HTTP connect is refused,
            # without stopping or modifying the Java service.
            reserved_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            reserved_socket.bind(("127.0.0.1", 0))
            connection_base_url = f"http://127.0.0.1:{reserved_socket.getsockname()[1]}"
        try:
            connection_client = JavaMarketClient(
                JavaMarketClientConfig(
                    base_url=connection_base_url,
                    timeout_seconds=0.2,
                    enable_dev_auth_header=True,
                )
            )
            connection_agent = OrderFactsOrchestrator(
                registry=ToolRegistry([OrderFactsTool(connection_client)]), compatibility_mode=True
            )
            connection = connection_agent.handle_message(
                "phase2b-live-connection", args.authorized_user, f"查询订单 {args.out_trade_no}"
            )
        finally:
            if reserved_socket:
                reserved_socket.close()
    finally:
        logger.removeHandler(capture)

    print(json.dumps({
        "positive": summarise(positive),
        "unauthorized": summarise(unauthorized),
        "no_auth": summarise(no_auth),
        "connection_failure": summarise(connection),
        # TraceEvent intentionally has no authenticated identity or HTTP headers.
        "trace": capture.events,
    }, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
