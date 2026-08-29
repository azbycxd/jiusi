from __future__ import annotations

import inspect

import pytest
from pydantic import BaseModel, ConfigDict, StrictStr, ValidationError

from agent.state import AgentState
from tools.arguments import OrderFactsArguments
from tools.base import AgentTool, RepeatPolicy
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import ToolResult


def successful_result() -> ToolResult:
    return ToolResult(success=True, message="ok", source="test")


def test_order_facts_tool_self_describes_its_contract() -> None:
    tool = OrderFactsTool(FakeMarketClient({}))
    assert isinstance(tool, AgentTool)
    assert tool.name == "get_order_facts"
    assert tool.description
    assert tool.arguments_schema is OrderFactsArguments
    assert tool.repeat_policy == RepeatPolicy(repeatable=True, max_same_call=2)
    schema = tool.arguments_schema.model_json_schema(by_alias=True)
    assert schema["required"] == ["outTradeNo"]
    assert schema["properties"]["outTradeNo"]["type"] == "string"
    assert schema["additionalProperties"] is False


def test_repeat_policy_requires_at_least_one_allowed_identical_call() -> None:
    with pytest.raises(ValidationError):
        RepeatPolicy(max_same_call=0)


def test_registry_describes_tools_from_metadata_without_business_branches() -> None:
    tool = OrderFactsTool(FakeMarketClient({}))
    registry = ToolRegistry([tool])
    assert registry.available_tools == (
        {
            "name": tool.name,
            "description": tool.description,
            "parameters_schema": tool.arguments_schema.model_json_schema(by_alias=True),
        },
    )
    assert "get_order_facts" not in inspect.getsource(ToolRegistry)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"outTradeNo": ""},
        {"outTradeNo": 123},
        {"outTradeNo": "644398015396", "userId": "xfg05"},
        {"outTradeNo": "644398015396", "authenticatedUserId": "xfg05"},
        {"outTradeNo": "644398015396", "headers": {"Authorization": "forbidden"}},
    ],
)
def test_order_facts_arguments_reject_invalid_or_privileged_fields(arguments: object) -> None:
    with pytest.raises(ValidationError):
        OrderFactsArguments.model_validate(arguments)


def test_registry_validates_arguments_and_passes_them_without_state_slot_dependency() -> None:
    expected = successful_result()
    market = FakeMarketClient({"644398015396": expected})
    registry = ToolRegistry([OrderFactsTool(market)])
    state = AgentState(session_id="tool-args", authenticated_user_id="trusted-user")
    assert state.out_trade_no is None

    arguments = registry.validate_arguments("get_order_facts", {"outTradeNo": " 644398015396 "})
    assert isinstance(arguments, OrderFactsArguments)
    result = registry.call("get_order_facts", state, arguments)

    assert result is expected
    assert len(market.calls) == 1
    assert market.calls[0][1] == "644398015396"
    assert market.calls[0][0].authenticated_user_id == "trusted-user"
    assert state.out_trade_no is None


def test_unknown_tool_stays_unavailable_at_validation_and_call_boundaries() -> None:
    registry = ToolRegistry([OrderFactsTool(FakeMarketClient({}))])
    state = AgentState(session_id="tool-unknown", authenticated_user_id="trusted-user")
    assert registry.validate_arguments("refund_order", {"outTradeNo": "644398015396"}) is None
    result = registry.call("refund_order", state, OrderFactsArguments(outTradeNo="644398015396"))
    assert (result.success, result.error_code) == (False, "TOOL_NOT_ALLOWED")


class DemoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: StrictStr


class DemoTool:
    name = "test_tool"
    description = "Test-only self-described tool."
    arguments_schema = DemoArguments
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)

    def run(self, state: AgentState, arguments: DemoArguments) -> ToolResult:
        return ToolResult(success=True, data={"value": arguments.value}, source="test_tool")


def test_registry_is_generic_for_a_second_self_described_test_tool() -> None:
    registry = ToolRegistry([DemoTool()])
    state = AgentState(session_id="generic-registry", authenticated_user_id="trusted-user")
    state.capability.allowed_tools = ("test_tool",)

    arguments = registry.validate_arguments("test_tool", {"value": "ok"})
    assert isinstance(arguments, DemoArguments)
    assert registry.call("test_tool", state, arguments).data == {"value": "ok"}
    assert registry.available_tools[0]["parameters_schema"]["required"] == ["value"]
    assert registry.repeat_policy("test_tool") == DemoTool.repeat_policy
