from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from agent.slots import validate_out_trade_no
from config.environment import load_project_env
from guardrails.auth_context import AuthContext
from tools.errors import ToolConnectionError, ToolTimeoutError, to_tool_result
from tools.facts import OrderFacts
from tools.base import MarketClient
from tools.schemas import Evidence, ToolResult


ORDER_FACTS_PATH = "/api/v1/agent/order/facts"


@dataclass(frozen=True)
class JavaMarketClientConfig:
    base_url: str | None
    timeout_seconds: float = 2.0
    enable_dev_auth_header: bool = False

    @classmethod
    def from_environment(cls) -> "JavaMarketClientConfig":
        load_project_env()
        raw_timeout = os.getenv("JAVA_MARKET_TIMEOUT_SECONDS", "2.0")
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError:
            timeout_seconds = 2.0
        return cls(
            base_url=os.getenv("JAVA_MARKET_BASE_URL") or None,
            timeout_seconds=timeout_seconds,
            enable_dev_auth_header=os.getenv("JAVA_MARKET_ENABLE_DEV_AUTH_HEADER", "false").lower() == "true",
        )


class JavaMarketClient:
    """Synchronous HTTP client for the contractually defined Java order-facts API."""

    source = "java_market"

    def __init__(self, config: JavaMarketClientConfig | None = None, http_client: httpx.Client | None = None) -> None:
        self._config = config or JavaMarketClientConfig.from_environment()
        # Java Market is a local/internal trust boundary; do not route it through
        # ambient proxy variables that can alter failure classification or identity flow.
        self._http_client = http_client or httpx.Client(timeout=self._config.timeout_seconds, trust_env=False)

    def get_order_facts(self, auth: AuthContext, out_trade_no: str) -> ToolResult:
        slot = validate_out_trade_no(out_trade_no)
        if not slot.is_valid:
            return ToolResult(
                success=False,
                error_code=slot.error_code,
                message="订单号无效或缺失",
                retryable=False,
                source=self.source,
            )
        if not self._config.base_url:
            return ToolResult.infrastructure_failure(
                "JAVA_MARKET_BASE_URL_NOT_CONFIGURED", "订单事实服务未配置", retryable=False, source=self.source
            )

        headers = {"Content-Type": "application/json"}
        if self._config.enable_dev_auth_header:
            headers["X-Dev-Authenticated-User-Id"] = auth.authenticated_user_id
        url = f"{self._config.base_url.rstrip('/')}{ORDER_FACTS_PATH}"
        try:
            response = self._http_client.post(url, json={"outTradeNo": slot.value}, headers=headers)
        except httpx.TimeoutException:
            return to_tool_result(ToolTimeoutError(), source=self.source)
        except httpx.ConnectError:
            return to_tool_result(ToolConnectionError(), source=self.source)
        except httpx.HTTPError:
            return ToolResult.infrastructure_failure(
                "HTTP_TRANSPORT_ERROR", "订单事实服务传输失败", retryable=True, source=self.source
            )
        except Exception:
            return to_tool_result(Exception(), source=self.source)

        if not 200 <= response.status_code < 300:
            return ToolResult.infrastructure_failure(
                "HTTP_UNEXPECTED_STATUS", "订单事实服务返回非预期状态", retryable=response.status_code >= 500, source=self.source
            )
        try:
            envelope = response.json()
        except ValueError:
            return ToolResult.infrastructure_failure(
                "TOOL_MALFORMED_JSON", "订单事实服务返回非法 JSON", retryable=False, source=self.source
            )
        if not isinstance(envelope, dict) or not isinstance(envelope.get("code"), str):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "订单事实服务响应契约不匹配", retryable=False, source=self.source
            )

        code = envelope["code"]
        if code == "0000":
            return self._success_from_data(envelope.get("data"))
        return self._error_for_java_code(code)

    def _success_from_data(self, data: Any) -> ToolResult:
        if not isinstance(data, dict):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "订单事实服务响应契约不匹配", retryable=False, source=self.source
            )
        try:
            facts = OrderFacts.model_validate(data)
        except ValidationError:
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "订单事实服务响应契约不匹配", retryable=False, source=self.source
            )
        facts_data = facts.as_context_data()
        evidence = [
            Evidence(kind="order.status", value=facts.order.status, source=self.source),
            Evidence(kind="team.status", value=facts.team.status, source=self.source),
            Evidence(kind="team.targetCount", value=str(facts.team.target_count), source=self.source),
            Evidence(kind="team.completeCount", value=str(facts.team.complete_count), source=self.source),
            Evidence(kind="activity.status", value=facts.activity.status, source=self.source),
        ]
        return ToolResult(success=True, message="订单事实获取成功", data={"facts": facts_data}, evidence=evidence, source=self.source)

    def _error_for_java_code(self, code: str) -> ToolResult:
        mapping: dict[str, tuple[bool, str]] = {
            "AUTH_REQUIRED": (False, "当前账号未完成订单事实查询认证"),
            "INVALID_ARGUMENT": (False, "订单事实查询参数无效"),
            "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED": (False, "订单不存在，或当前账号无权查看该订单"),
            "INTERNAL_SERVICE_ERROR": (True, "订单事实服务暂时不可用"),
        }
        if code in mapping:
            retryable, message = mapping[code]
            return ToolResult.infrastructure_failure(code, message, retryable=retryable, source=self.source)
        return ToolResult.infrastructure_failure(
            "TOOL_UNKNOWN_RESPONSE_CODE", "订单事实服务返回未知结果码", retryable=False, source=self.source
        )


class OrderFactsTool:
    name = "get_order_facts"

    def __init__(self, client: MarketClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    def run(self, state) -> ToolResult:
        slot = validate_out_trade_no(state.out_trade_no)
        if not slot.is_valid:
            return ToolResult(
                success=False,
                error_code=slot.error_code,
                message="订单号无效或缺失",
                retryable=False,
                source=self.name,
            )
        if not isinstance(state.authenticated_user_id, str) or not state.authenticated_user_id.strip():
            return ToolResult.infrastructure_failure(
                "AUTH_REQUIRED", "缺少可信认证身份，无法查询订单事实", retryable=False, source=self.name
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_order_facts(auth=auth, out_trade_no=slot.value)
        except Exception as error:
            return to_tool_result(error, source=self.name)
