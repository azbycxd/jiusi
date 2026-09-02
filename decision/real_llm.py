from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from config.environment import load_project_env
from decision.errors import (
    ModelConnectionError,
    ModelHttpError,
    ModelInvalidResponseError,
    ModelRateLimitedError,
    ModelTimeoutError,
)
from decision.schemas import DecisionContext
from decision.telemetry import ModelTelemetry


SYSTEM_PROMPT = """You are the decision module for a group-buy customer-service Agent.
Do not operate databases or systems. Use only the user query, business facts, evidence,
and allowed tools provided in the current context. Choose exactly one next action:
CALL_TOOL, ANSWER, REQUEST_INPUT, or HANDOFF.

Return one JSON object only. Choose exactly one action and output only that action's fields:
CALL_TOOL: action, tool_name, tool_arguments.
ANSWER: action, final_answer, used_evidence.
REQUEST_INPUT: action, missing_information.
HANDOFF: action, missing_information.

The available_tools list is the complete set of capabilities you can execute,
not examples. Never assume an unlisted tool, business query, real-time source,
or rule knowledge exists. If a required fact can be obtained by an available
tool but its required user-supplied parameter is absent, choose REQUEST_INPUT
and name only the missing parameter. If the required fact, rule, or capability
cannot be obtained by an available tool, choose HANDOFF and name the missing
information.

Classify the request by the information needed to complete it, not by keywords.
General rules, concepts, and status meanings may be answered when the available
rule evidence is sufficient. A question about a particular user, order, team,
activity, refund, payment, qualification, status, result, time, or amount asks
for an instance fact. ANSWER only when validated Tool observations can verify
the requested instance fact. General rule knowledge may explain boundaries but
can never substitute for missing instance facts. If an instance fact cannot be
verified with the available tools and observations, choose REQUEST_INPUT when a
user-supplied Tool parameter would make verification possible; otherwise choose
HANDOFF even when a limited reply could say that it cannot be confirmed; list
the missing fact or capability in missing_information.

This Agent is limited to group-buy customer service and order diagnosis. ANSWER
only when the request is within that product responsibility, is a supported
general rule explanation, or asks about the Agent's current available
capabilities. Requests outside that responsibility, or requests to control
identity, authentication, headers, transport, databases, or other runtime
internals, must choose HANDOFF. A refusal or a general-purpose reply is not an
ANSWER that completes an out-of-scope request.
This mandatory HANDOFF takes precedence over REQUEST_INPUT: do not request an
additional parameter in order to continue a request for runtime control.

Do not output irrelevant fields as null, empty strings, empty objects, or empty arrays;
omit them entirely. REQUEST_INPUT and HANDOFF are control only: never include a
user-facing business answer.

For CALL_TOOL, request only an allowed tool. Its arguments must conform exactly to that
tool's published parameters_schema. Use argument values only when they are explicitly in
the user query or in validated observations/evidence, and only when they match the chosen
tool's schema; never guess or fabricate missing arguments. Never provide userId,
authenticated_user_id, token, headers, auth context, SQL, or base_url.
The available_tools list is runtime capability metadata, not business evidence. For every
ANSWER, used_evidence may contain only paths that exist in DecisionContext.evidence. Copy
the exact string from an evidence entry's kind field; never cite an array position such as
evidence[0]. Never cite available_tools metadata, tool descriptions, parameters_schema, the
system prompt, the user query, or authentication/runtime metadata. An answer that only explains current Agent
capabilities may use available_tools metadata and must set used_evidence to []. An answer
that states business facts obtained from a tool must cite the corresponding
DecisionContext.evidence paths. Do not invent payment, refund, notification, other-user,
database, or Java facts. Use HANDOFF when the available tools and facts cannot safely answer.
For a multi-step answer, used_evidence must cover the business facts actually
stated or materially relied upon by the final answer. Tool argument provenance
is validated separately: when a later Tool argument comes from an earlier
Observation, do not cite that intermediate value unless the final answer itself
states or relies on it as a business fact. Do not cite every Observation by
default; cite only facts materially relied upon.

For an open-ended diagnostic question about why something failed or why a user
cannot participate, one verified condition is not automatically a complete
diagnosis. Before ANSWER, check whether another independent cause dimension
directly relevant to the question remains unverified and can be checked by an
available tool. If so, CALL_TOOL for the most relevant next information need.
Choose that next tool from the user query, the current observations, and the
unverified information; do not assume a fixed tool order or call every tool.
Do not use a rule lookup unless a rule explanation is actually needed. If the
remaining required information cannot be verified with available tools, choose
HANDOFF.
Once current observations sufficiently explain the diagnostic scope, ANSWER
instead of exploring an unrelated available capability merely because it exists.
Do not output chain-of-thought or internal reasoning."""


@dataclass(frozen=True)
class RealLLMConfig:
    """Configuration for an OpenAI-compatible chat-completions provider."""

    model: str | None
    api_key: str | None
    base_url: str | None
    timeout_seconds: float = 10.0

    @classmethod
    def from_environment(cls) -> "RealLLMConfig":
        load_project_env()
        raw_timeout = os.getenv("LLM_TIMEOUT")
        if raw_timeout is None or not raw_timeout.strip():
            timeout = 10.0
        else:
            try:
                timeout = float(raw_timeout)
            except ValueError as error:
                raise ValueError("LLM_TIMEOUT must be a number") from error
        return cls(
            model=os.getenv("LLM_MODEL") or None,
            api_key=os.getenv("LLM_API_KEY") or None,
            base_url=os.getenv("LLM_BASE_URL") or None,
            timeout_seconds=timeout,
        )

    @property
    def has_any_value(self) -> bool:
        return any((self.model, self.api_key, self.base_url))

    def validate(self) -> None:
        if not self.model or not self.api_key or not self.base_url:
            raise ValueError("LLM_MODEL, LLM_API_KEY, and LLM_BASE_URL must all be configured")
        if self.timeout_seconds <= 0:
            raise ValueError("LLM_TIMEOUT must be greater than zero")


class RealLLMDecisionModel:
    """Synchronous, mockable OpenAI-compatible DecisionModel implementation."""

    def __init__(self, config: RealLLMConfig | None = None, http_client: httpx.Client | None = None) -> None:
        self._config = config or RealLLMConfig.from_environment()
        self._config.validate()
        self._http_client = http_client or httpx.Client(timeout=self._config.timeout_seconds, trust_env=False)
        self.last_telemetry: ModelTelemetry | None = None

    @property
    def model_name(self) -> str:
        return self._config.model or ""

    def build_payload(self, context: DecisionContext) -> dict[str, Any]:
        """Build the complete provider body from the deliberately minimal DecisionContext."""
        visible_context = {
            "user_query": context.user_query,
            "diagnosis_progress": context.diagnosis_progress.model_dump(mode="json") if context.diagnosis_progress else None,
            "available_tools": [tool.model_dump(mode="json") for tool in context.available_tools],
            "observations": [item.model_dump(mode="json") for item in context.observations],
            "evidence": context.evidence,
        }
        return {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(visible_context, ensure_ascii=False)},
            ],
        }

    def decide(self, context: DecisionContext) -> object:
        self.last_telemetry = None
        try:
            response = self._http_client.post(
                self._endpoint(),
                json=self.build_payload(context),
                headers={"Authorization": f"Bearer {self._config.api_key}", "Content-Type": "application/json"},
            )
        except httpx.TimeoutException as error:
            raise ModelTimeoutError() from error
        except httpx.ConnectError as error:
            raise ModelConnectionError() from error
        except httpx.HTTPError as error:
            raise ModelHttpError() from error

        if response.status_code == 429:
            raise ModelRateLimitedError()
        if not 200 <= response.status_code < 300:
            error = ModelHttpError()
            error.retryable = response.status_code >= 500
            raise error
        try:
            payload = response.json()
        except ValueError as error:
            raise ModelInvalidResponseError() from error
        content = self._content_from_payload(payload)
        self.last_telemetry = self._telemetry_from_payload(payload)
        if isinstance(content, dict):
            return content
        if not isinstance(content, str) or not content.strip():
            raise ModelInvalidResponseError()
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError) as error:
            raise ModelInvalidResponseError() from error
        if not isinstance(parsed, dict):
            raise ModelInvalidResponseError()
        return parsed

    def _endpoint(self) -> str:
        assert self._config.base_url
        base_url = self._config.base_url.rstrip("/")
        return base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"

    @staticmethod
    def _content_from_payload(payload: Any) -> Any:
        if not isinstance(payload, dict):
            raise ModelInvalidResponseError()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelInvalidResponseError()
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelInvalidResponseError()
        return message.get("content")

    def _telemetry_from_payload(self, payload: dict[str, Any]) -> ModelTelemetry:
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return ModelTelemetry(
            model=str(payload.get("model") or self._config.model),
            input_tokens=self._safe_int(usage.get("prompt_tokens")),
            output_tokens=self._safe_int(usage.get("completion_tokens")),
            total_tokens=self._safe_int(usage.get("total_tokens")),
        )

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        return value if isinstance(value, int) and value >= 0 else None
