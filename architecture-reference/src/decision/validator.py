"""Provider JSON → 规范 Decision；严格拒绝多余字段。"""
from .actions import DecisionAction
from .schemas import (AnswerDecision, HandoffDecision, RequestInputDecision,
                      ToolCallDecision)


class DecisionValidationError(ValueError):
    pass


class DecisionValidator:
    ALLOWED = {
        DecisionAction.CALL_TOOL: {"action", "tool_name", "tool_arguments"},
        DecisionAction.ANSWER: {"action", "answer", "used_evidence"},
        DecisionAction.REQUEST_INPUT: {"action", "missing_information", "question"},
        DecisionAction.HANDOFF: {"action", "reason_code", "message"},
    }

    def parse(self, raw):
        """接受 mapping 或已构造对象；mapping 执行 extra field reject。"""
        if not isinstance(raw, dict):
            return self.validate(raw)
        try:
            action = DecisionAction(raw.get("action"))
        except (TypeError, ValueError):
            raise DecisionValidationError("未知 Decision action") from None
        if set(raw) != self.ALLOWED[action]:
            raise DecisionValidationError("Decision 字段缺失或包含额外字段")
        if action is DecisionAction.CALL_TOOL:
            decision = ToolCallDecision(tool_name=raw["tool_name"], tool_arguments=raw["tool_arguments"])
        elif action is DecisionAction.ANSWER:
            decision = AnswerDecision(raw["answer"], tuple(raw["used_evidence"]))
        elif action is DecisionAction.REQUEST_INPUT:
            decision = RequestInputDecision(tuple(raw["missing_information"]), raw["question"])
        else:
            decision = HandoffDecision(raw["reason_code"], raw["message"])
        return self.validate(decision)

    def validate(self, decision):
        action = getattr(decision, "action", None)
        if action is DecisionAction.CALL_TOOL:
            if not isinstance(decision.tool_name, str) or not decision.tool_name.strip():
                raise DecisionValidationError("CALL_TOOL 缺少 tool_name")
            if not isinstance(decision.tool_arguments, dict):
                raise DecisionValidationError("tool_arguments 必须是对象")
        elif action is DecisionAction.ANSWER:
            if not isinstance(decision.final_answer, str) or not decision.final_answer.strip():
                raise DecisionValidationError("ANSWER 缺少 answer")
            if not isinstance(decision.used_evidence, tuple) or not decision.used_evidence:
                raise DecisionValidationError("ANSWER 缺少 used_evidence")
        elif action is DecisionAction.REQUEST_INPUT:
            if not decision.missing_information or not str(decision.question).strip():
                raise DecisionValidationError("REQUEST_INPUT 字段不完整")
        elif action is DecisionAction.HANDOFF:
            if not str(decision.reason_code).strip() or not str(decision.message).strip():
                raise DecisionValidationError("HANDOFF 字段不完整")
        else:
            raise DecisionValidationError("Decision 对象类型非法")
        return decision


def validate_decision(decision):
    """保留上一批函数入口。"""
    return DecisionValidator().parse(decision)
