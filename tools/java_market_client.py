from __future__ import annotations

from diagnosis.reason_codes import ReasonCode
from guardrails.auth_context import AuthContext
from agent.slots import validate_out_trade_no
from tools.errors import ToolTimeoutError, to_tool_result
from tools.schemas import Evidence, ToolResult


class JavaMarketClient:
    """V1 stub for the future high-level Java read facade.

    The method deliberately receives trusted AuthContext, not an LLM-produced user id.
    """

    source = "java_market_facade_stub"

    def get_order_diagnosis(self, auth: AuthContext, out_trade_no: str) -> ToolResult:
        del auth  # Identity is consumed by the facade in the real implementation.
        fixtures: dict[str, ToolResult] = {
            "202608240001": self._success(ReasonCode.GROUP_IN_PROGRESS),
            "202608240004": ToolResult(success=False, error_code="ORDER_NOT_FOUND_OR_NOT_AUTHORIZED", message="订单不可见", source=self.source),
            "202608240005": ToolResult.infrastructure_failure("JAVA_TEMPORARILY_UNAVAILABLE", "Java 服务暂时不可用", retryable=True, source=self.source),
            "202608240006": ToolResult.infrastructure_failure("JAVA_REQUEST_REJECTED", "Java 服务拒绝本次查询", retryable=False, source=self.source),
            "202608240007": self._success("FUTURE_REASON_CODE"),
            "202608240008": ToolTimeoutError(),
        }
        fixture = fixtures.get(out_trade_no, self._success(ReasonCode.GROUP_IN_PROGRESS))
        if isinstance(fixture, Exception):
            raise fixture
        return fixture

    def _success(self, reason_code: ReasonCode | str) -> ToolResult:
        code = reason_code.value if isinstance(reason_code, ReasonCode) else reason_code
        return ToolResult(
            success=True,
            message="诊断完成",
            data={"reasonCode": code},
            evidence=[Evidence(kind="reason_code", value=code, source=self.source)],
            source=self.source,
        )


class GetOrderDiagnosisTool:
    name = "get_order_diagnosis"

    def __init__(self, client: JavaMarketClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    def run(self, state) -> ToolResult:
        slot = validate_out_trade_no(state.out_trade_no)
        if not slot.is_valid:
            return ToolResult(
                success=False,
                error_code=slot.error_code,
                message="订单号无效或缺失",
                retryable=False,
                source="get_order_diagnosis",
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_order_diagnosis(auth=auth, out_trade_no=slot.value)
        except Exception as error:
            return to_tool_result(error, source="get_order_diagnosis")
