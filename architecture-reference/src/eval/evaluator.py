"""【B 架构重构】Agent 结果的确定性 Contract Eval。"""
from dataclasses import dataclass
from enum import Enum
from .failure_classifier import FailureKind


class EvalStatus(str,Enum): PASS="PASS"; FAIL="FAIL"; INFRA_FAILURE="INFRA_FAILURE"


@dataclass(frozen=True)
class EvalResult:
    case_id:str
    status:EvalStatus
    failures:tuple[str,...]=()
    failure_kind:FailureKind|None=None


class AgentEvaluator:
    def evaluate(self,case,result):
        if getattr(result,"infrastructure_failure",False):
            return EvalResult(case.case_id,EvalStatus.INFRA_FAILURE,
                              ("INFRASTRUCTURE_UNAVAILABLE",),FailureKind.INFRA_FAILURE)
        failures=[]
        action=getattr(getattr(result,"final_action",None),"value",getattr(result,"final_action",None))
        tools=tuple(getattr(result,"tool_sequence",()))
        evidence=tuple(getattr(result,"used_evidence",()))
        if action!=case.expected_action: failures.append("UNEXPECTED_ACTION")
        if not set(case.required_tools)<=set(tools): failures.append("MISSING_REQUIRED_TOOL")
        if set(case.forbidden_tools)&set(tools): failures.append("FORBIDDEN_TOOL")
        if getattr(result,"tool_call_count",len(tools))>case.max_tool_calls: failures.append("TOOL_BUDGET_EXCEEDED")
        if any(not any(item.startswith(prefix) for item in evidence) for prefix in case.required_evidence): failures.append("MISSING_EVIDENCE")
        kind=FailureKind.EVIDENCE_FAILURE if "MISSING_EVIDENCE" in failures else (FailureKind.BUSINESS_FAILURE if failures else None)
        return EvalResult(case.case_id,EvalStatus.FAIL if failures else EvalStatus.PASS,tuple(failures),kind)


def evaluate(case,result):
    """兼容早期返回字符串的入口。"""
    return AgentEvaluator().evaluate(case,result).status.value
