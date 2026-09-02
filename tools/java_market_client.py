from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from agent.slots import validate_out_trade_no
from agent.state import AgentState
from config.environment import load_project_env
from guardrails.auth_context import AuthContext
from tools.base import (
    ActivityFactsClient,
    JoinableTeamFactsClient,
    MarketClient,
    RepeatPolicy,
    UserEligibilityFactsClient,
)
from tools.arguments import (
    ActivityFactsArguments,
    JoinableTeamFactsArguments,
    OrderFactsArguments,
    UserEligibilityFactsArguments,
)
from tools.errors import ToolConnectionError, ToolTimeoutError, to_tool_result
from tools.facts import ActivityFactsResponse, JoinableTeamFacts, OrderFacts, UserEligibilityFacts
from tools.schemas import Evidence, ToolResult


ORDER_FACTS_PATH = "/api/v1/agent/order/facts"
JOINABLE_TEAM_FACTS_PATH = "/api/v1/agent/team/joinable-facts"
ACTIVITY_FACTS_PATH = "/api/v1/agent/activity/facts"
USER_ELIGIBILITY_FACTS_PATH = "/api/v1/agent/activity/eligibility-facts"


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
    """Synchronous HTTP client for contractually defined, read-only Java facts APIs."""

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
        envelope = self._post_envelope(ORDER_FACTS_PATH, auth, {"outTradeNo": slot.value})
        if isinstance(envelope, ToolResult):
            return envelope
        code = envelope["code"]
        if code == "0000":
            return self._success_from_data(envelope.get("data"))
        return self._error_for_java_code(code)

    def get_joinable_team_facts(self, auth: AuthContext, activity_id: int) -> ToolResult:
        if type(activity_id) is not int or activity_id <= 0:
            return ToolResult.infrastructure_failure(
                "INVALID_ARGUMENT", "活动 ID 无效或缺失", retryable=False, source=self.source
            )
        envelope = self._post_envelope(JOINABLE_TEAM_FACTS_PATH, auth, {"activityId": activity_id})
        if isinstance(envelope, ToolResult):
            return envelope
        code = envelope["code"]
        if code == "0000":
            return self._joinable_team_success_from_data(envelope.get("data"))
        return self._error_for_java_code(code)

    def get_activity_facts(self, auth: AuthContext, activity_id: int) -> ToolResult:
        if type(activity_id) is not int or activity_id <= 0:
            return ToolResult.infrastructure_failure(
                "INVALID_ARGUMENT", "活动 ID 无效或缺失", retryable=False, source=self.source
            )
        envelope = self._post_envelope(ACTIVITY_FACTS_PATH, auth, {"activityId": activity_id})
        if isinstance(envelope, ToolResult):
            return envelope
        code = envelope["code"]
        if code == "0000":
            return self._activity_success_from_data(envelope.get("data"))
        return self._error_for_java_code(code)

    def get_user_eligibility_facts(self, auth: AuthContext, activity_id: int) -> ToolResult:
        if type(activity_id) is not int or activity_id <= 0:
            return ToolResult.infrastructure_failure(
                "INVALID_ARGUMENT", "活动 ID 无效或缺失", retryable=False, source=self.source
            )
        envelope = self._post_envelope(USER_ELIGIBILITY_FACTS_PATH, auth, {"activityId": activity_id})
        if isinstance(envelope, ToolResult):
            return envelope
        code = envelope["code"]
        if code == "0000":
            return self._eligibility_success_from_data(envelope.get("data"))
        return self._error_for_java_code(code)

    def _post_envelope(self, path: str, auth: AuthContext, body: dict[str, object]) -> dict[str, Any] | ToolResult:
        """Shared transport, JSON, and Java-envelope boundary for read-only facts APIs."""
        if not self._config.base_url:
            return ToolResult.infrastructure_failure(
                "JAVA_MARKET_BASE_URL_NOT_CONFIGURED", "市场事实服务未配置", retryable=False, source=self.source
            )
        headers = {"Content-Type": "application/json"}
        if self._config.enable_dev_auth_header:
            headers["X-Dev-Authenticated-User-Id"] = auth.authenticated_user_id
        url = f"{self._config.base_url.rstrip('/')}{path}"
        try:
            response = self._http_client.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            return to_tool_result(ToolTimeoutError(), source=self.source)
        except httpx.ConnectError:
            return to_tool_result(ToolConnectionError(), source=self.source)
        except httpx.HTTPError:
            return ToolResult.infrastructure_failure(
                "HTTP_TRANSPORT_ERROR", "市场事实服务传输失败", retryable=True, source=self.source
            )
        except Exception:
            return to_tool_result(Exception(), source=self.source)
        if not 200 <= response.status_code < 300:
            return ToolResult.infrastructure_failure(
                "HTTP_UNEXPECTED_STATUS", "市场事实服务返回非预期状态", retryable=response.status_code >= 500, source=self.source
            )
        try:
            envelope = response.json()
        except ValueError:
            return ToolResult.infrastructure_failure(
                "TOOL_MALFORMED_JSON", "市场事实服务返回非法 JSON", retryable=False, source=self.source
            )
        if not isinstance(envelope, dict) or not isinstance(envelope.get("code"), str):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "市场事实服务响应契约不匹配", retryable=False, source=self.source
            )
        return envelope

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
            Evidence(kind="team.target_count", value=str(facts.team.target_count), source=self.source),
            Evidence(kind="team.complete_count", value=str(facts.team.complete_count), source=self.source),
            Evidence(kind="activity.status", value=facts.activity.status, source=self.source),
        ]
        return ToolResult(success=True, message="订单事实获取成功", data=facts_data, evidence=evidence, source=self.source)

    def _joinable_team_success_from_data(self, data: Any) -> ToolResult:
        if not isinstance(data, dict):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "可加入团队事实服务响应契约不匹配", retryable=False, source=self.source
            )
        try:
            facts = JoinableTeamFacts.model_validate(data)
        except ValidationError:
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "可加入团队事实服务响应契约不匹配", retryable=False, source=self.source
            )
        evidence = [
            Evidence(kind="activity_id", value=str(facts.activity_id), source=self.source),
            Evidence(kind="statistics.all_team_count", value=str(facts.statistics.all_team_count), source=self.source),
            Evidence(
                kind="statistics.all_team_complete_count",
                value=str(facts.statistics.all_team_complete_count),
                source=self.source,
            ),
            Evidence(kind="statistics.all_team_user_count", value=str(facts.statistics.all_team_user_count), source=self.source),
        ]
        if not facts.candidate_teams:
            evidence.append(
                Evidence(kind="candidate_teams", value=str(facts.candidate_teams), source=self.source)
            )
        for index, team in enumerate(facts.candidate_teams):
            prefix = f"candidate_teams.{index}"
            evidence.extend([
                Evidence(kind=f"{prefix}.team_id", value=team.team_id, source=self.source),
                Evidence(kind=f"{prefix}.target_count", value=str(team.target_count), source=self.source),
                Evidence(kind=f"{prefix}.complete_count", value=str(team.complete_count), source=self.source),
                Evidence(kind=f"{prefix}.lock_count", value=str(team.lock_count), source=self.source),
            ])
            if team.valid_end_time is not None:
                evidence.append(Evidence(kind=f"{prefix}.valid_end_time", value=team.valid_end_time, source=self.source))
        return ToolResult(
            success=True,
            message="可加入团队事实获取成功",
            data=facts.as_context_data(),
            evidence=evidence,
            source=self.source,
        )

    def _activity_success_from_data(self, data: Any) -> ToolResult:
        if not isinstance(data, dict):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "活动事实服务响应契约不匹配", retryable=False, source=self.source
            )
        try:
            facts = ActivityFactsResponse.model_validate(data)
        except ValidationError:
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "活动事实服务响应契约不匹配", retryable=False, source=self.source
            )
        activity = facts.activity
        evidence = [
            Evidence(kind="activity.activity_id", value=str(activity.activity_id), source=self.source),
            Evidence(kind="activity.status", value=activity.status, source=self.source),
            Evidence(kind="activity.start_time", value=activity.start_time, source=self.source),
            Evidence(kind="activity.end_time", value=activity.end_time, source=self.source),
            Evidence(kind="activity.tag_scope", value=activity.tag_scope, source=self.source),
            Evidence(kind="activity.evaluated_at", value=activity.evaluated_at, source=self.source),
            Evidence(kind="activity.within_valid_time", value=str(activity.within_valid_time), source=self.source),
        ]
        if activity.user_take_limit is not None:
            evidence.append(Evidence(
                kind="activity.user_take_limit", value=str(activity.user_take_limit), source=self.source
            ))
        return ToolResult(
            success=True,
            message="活动事实获取成功",
            data=facts.as_context_data(),
            evidence=evidence,
            source=self.source,
        )

    def _eligibility_success_from_data(self, data: Any) -> ToolResult:
        if not isinstance(data, dict):
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "用户参与资格事实服务响应契约不匹配", retryable=False, source=self.source
            )
        try:
            facts = UserEligibilityFacts.model_validate(data)
        except ValidationError:
            return ToolResult.infrastructure_failure(
                "TOOL_CONTRACT_MISMATCH", "用户参与资格事实服务响应契约不匹配", retryable=False, source=self.source
            )
        evidence = [
            Evidence(kind="activity_id", value=str(facts.activity_id), source=self.source),
            Evidence(kind="tag_rule_configured", value=str(facts.tag_rule_configured), source=self.source),
            Evidence(kind="tag_crowd_data_available", value=str(facts.tag_crowd_data_available), source=self.source),
            Evidence(kind="tag_gate_passed", value=str(facts.tag_gate_passed), source=self.source),
            Evidence(kind="tag_visibility_allowed", value=str(facts.tag_visibility_allowed), source=self.source),
            Evidence(kind="tag_participation_allowed", value=str(facts.tag_participation_allowed), source=self.source),
            Evidence(kind="user_take_count", value=str(facts.user_take_count), source=self.source),
            Evidence(kind="participation_limit_reached", value=str(facts.participation_limit_reached), source=self.source),
            Evidence(kind="market_downgraded", value=str(facts.market_downgraded), source=self.source),
            Evidence(kind="user_within_release_range", value=str(facts.user_within_release_range), source=self.source),
        ]
        if facts.user_take_limit is not None:
            evidence.append(Evidence(kind="user_take_limit", value=str(facts.user_take_limit), source=self.source))
        return ToolResult(
            success=True,
            message="当前用户参与资格事实获取成功",
            data=facts.as_context_data(),
            evidence=evidence,
            source=self.source,
        )

    def _error_for_java_code(self, code: str) -> ToolResult:
        mapping: dict[str, tuple[bool, str]] = {
            "AUTH_REQUIRED": (False, "当前账号未完成市场事实查询认证"),
            "INVALID_ARGUMENT": (False, "市场事实查询参数无效"),
            "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED": (False, "订单不存在，或当前账号无权查看该订单"),
            "ACTIVITY_NOT_FOUND": (False, "活动不存在或当前账号无权查看该活动"),
            "INTERNAL_SERVICE_ERROR": (True, "市场事实服务暂时不可用"),
        }
        if code in mapping:
            retryable, message = mapping[code]
            return ToolResult.infrastructure_failure(code, message, retryable=retryable, source=self.source)
        return ToolResult.infrastructure_failure(
            "TOOL_UNKNOWN_RESPONSE_CODE", "市场事实服务返回未知结果码", retryable=False, source=self.source
        )


class OrderFactsTool:
    name = "get_order_facts"
    description = "Read trusted order, team, activity, and reference facts for an external order number."
    arguments_schema = OrderFactsArguments
    repeat_policy = RepeatPolicy(repeatable=True, max_same_call=2)

    def __init__(self, client: MarketClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    @staticmethod
    def arguments_from_legacy_state(state: AgentState) -> OrderFactsArguments | None:
        """Phase 2B compatibility adapter; normal LLM Tool calls never read this slot."""
        if state.out_trade_no is None:
            return None
        try:
            return OrderFactsArguments(outTradeNo=state.out_trade_no)
        except ValidationError:
            return None

    def run(self, state: AgentState, arguments: OrderFactsArguments) -> ToolResult:
        if not isinstance(state.authenticated_user_id, str) or not state.authenticated_user_id.strip():
            return ToolResult.infrastructure_failure(
                "AUTH_REQUIRED", "缺少可信认证身份，无法查询订单事实", retryable=False, source=self.name
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_order_facts(auth=auth, out_trade_no=arguments.out_trade_no)
        except Exception as error:
            return to_tool_result(error, source=self.name)


class JoinableTeamFactsTool:
    name = "get_joinable_team_facts"
    description = (
        "Read real-time candidate teams a user can join for an activity and that activity's existing "
        "team statistics. Input: activityId. Statistics are activity-wide facts, not a candidate-team count."
    )
    arguments_schema = JoinableTeamFactsArguments
    repeat_policy = RepeatPolicy(repeatable=True, max_same_call=2)

    def __init__(self, client: JoinableTeamFactsClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    def run(self, state: AgentState, arguments: JoinableTeamFactsArguments) -> ToolResult:
        if not isinstance(state.authenticated_user_id, str) or not state.authenticated_user_id.strip():
            return ToolResult.infrastructure_failure(
                "AUTH_REQUIRED", "缺少可信认证身份，无法查询可加入团队事实", retryable=False, source=self.name
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_joinable_team_facts(auth=auth, activity_id=arguments.activity_id)
        except Exception as error:
            return to_tool_result(error, source=self.name)


class ActivityFactsTool:
    name = "get_activity_facts"
    # Internal completion metadata only; it is not exposed in the LLM Tool schema.
    diagnosis_dimension = "activity"
    description = (
        "Read real-time activity-level status, configured time window, tag scope, and participation limit facts "
        "for an existing activityId. Use when activity status or time configuration is needed."
    )
    arguments_schema = ActivityFactsArguments
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)

    def __init__(self, client: ActivityFactsClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    def run(self, state: AgentState, arguments: ActivityFactsArguments) -> ToolResult:
        if not isinstance(state.authenticated_user_id, str) or not state.authenticated_user_id.strip():
            return ToolResult.infrastructure_failure(
                "AUTH_REQUIRED", "缺少可信认证身份，无法查询活动事实", retryable=False, source=self.name
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_activity_facts(auth=auth, activity_id=arguments.activity_id)
        except Exception as error:
            return to_tool_result(error, source=self.name)


class UserEligibilityFactsTool:
    name = "get_user_eligibility_facts"
    # Internal completion metadata only; it is not exposed in the LLM Tool schema.
    diagnosis_dimension = "eligibility"
    description = (
        "Read current authenticated user's participation eligibility facts for an existing activityId, including "
        "tag gates, participation counts, downgrade, and release-range constraints."
    )
    arguments_schema = UserEligibilityFactsArguments
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)

    def __init__(self, client: UserEligibilityFactsClient | None = None) -> None:
        self._client = client or JavaMarketClient()

    def run(self, state: AgentState, arguments: UserEligibilityFactsArguments) -> ToolResult:
        if not isinstance(state.authenticated_user_id, str) or not state.authenticated_user_id.strip():
            return ToolResult.infrastructure_failure(
                "AUTH_REQUIRED", "缺少可信认证身份，无法查询当前用户参与资格事实", retryable=False, source=self.name
            )
        auth = AuthContext(authenticated_user_id=state.authenticated_user_id)
        try:
            return self._client.get_user_eligibility_facts(auth=auth, activity_id=arguments.activity_id)
        except Exception as error:
            return to_tool_result(error, source=self.name)
