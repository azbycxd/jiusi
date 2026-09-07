"""严格 Decision 数据结构；不携带隐藏思维过程。"""
from dataclasses import dataclass, field
from typing import TypeAlias
from .actions import DecisionAction


@dataclass(frozen=True)
class Decision:
    """兼容入口；Validator 会将其规范化为具体动作类型。"""
    action: DecisionAction
    tool_name: str | None = None
    tool_arguments: dict = field(default_factory=dict)
    final_answer: str | None = None
    used_evidence: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    question: str | None = None
    reason_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class ToolCallDecision:
    action: DecisionAction = field(default=DecisionAction.CALL_TOOL, init=False)
    tool_name: str = ""
    tool_arguments: dict = field(default_factory=dict)
    final_answer: None = field(default=None, init=False)
    used_evidence: tuple = field(default=(), init=False)
    missing_information: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class AnswerDecision:
    action: DecisionAction = field(default=DecisionAction.ANSWER, init=False)
    final_answer: str = ""
    used_evidence: tuple[str, ...] = ()
    tool_name: None = field(default=None, init=False)
    tool_arguments: dict = field(default_factory=dict, init=False)
    missing_information: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class RequestInputDecision:
    action: DecisionAction = field(default=DecisionAction.REQUEST_INPUT, init=False)
    missing_information: tuple[str, ...] = ()
    question: str = ""
    tool_name: None = field(default=None, init=False)
    tool_arguments: dict = field(default_factory=dict, init=False)
    final_answer: None = field(default=None, init=False)
    used_evidence: tuple = field(default=(), init=False)


@dataclass(frozen=True)
class HandoffDecision:
    action: DecisionAction = field(default=DecisionAction.HANDOFF, init=False)
    reason_code: str = "CAPABILITY_UNAVAILABLE"
    message: str = "当前能力无法可靠继续，建议转人工。"
    tool_name: None = field(default=None, init=False)
    tool_arguments: dict = field(default_factory=dict, init=False)
    final_answer: None = field(default=None, init=False)
    used_evidence: tuple = field(default=(), init=False)
    missing_information: tuple = field(default=(), init=False)


AgentDecision: TypeAlias = ToolCallDecision | AnswerDecision | RequestInputDecision | HandoffDecision
