"""模型可提议的四种动作；执行权始终属于 Harness/Orchestrator。"""
from enum import Enum


class DecisionAction(str, Enum):
    CALL_TOOL = "CALL_TOOL"
    ANSWER = "ANSWER"
    REQUEST_INPUT = "REQUEST_INPUT"
    HANDOFF = "HANDOFF"


Action = DecisionAction
