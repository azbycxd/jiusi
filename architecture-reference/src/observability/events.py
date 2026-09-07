"""【B 架构重构】Trace、Span 与 Event 的安全结构。"""
from dataclasses import dataclass,field
from enum import Enum
from typing import Any


class SpanType(str,Enum):
    REQUEST="REQUEST"; ROUTING="ROUTING"; SKILL_LOAD="SKILL_LOAD"
    CONTEXT_BUILD="CONTEXT_BUILD"; MODEL_CALL="MODEL_CALL"
    DECISION_VALIDATION="DECISION_VALIDATION"; TOOL_CALL="TOOL_CALL"
    TOOL_RESULT="TOOL_RESULT"; OBSERVATION="OBSERVATION"
    PROGRESS_UPDATE="PROGRESS_UPDATE"; COMPLETION="COMPLETION"
    FINAL_ANSWER="FINAL_ANSWER"; HANDOFF="HANDOFF"; ERROR="ERROR"


class SpanStatus(str,Enum): OK="OK"; ERROR="ERROR"; CANCELLED="CANCELLED"


@dataclass(frozen=True)
class TraceEvent:
    trace_id:str
    stage:str
    action:str
    session_id:str|None=None
    task_id:str|None=None
    skill_name:str|None=None
    tool_name:str|None=None
    error_code:str|None=None
    duration_ms:float=0.0
    metadata:dict[str,Any]=field(default_factory=dict)
    span_id:str|None=None
    parent_span_id:str|None=None
    timestamp:str|None=None


@dataclass(frozen=True)
class TraceSpan:
    trace_id:str
    span_id:str
    parent_span_id:str|None
    span_type:SpanType
    session_id:str|None
    task_id:str|None
    skill_name:str|None
    start_time:str
    end_time:str|None=None
    duration_ms:float|None=None
    status:SpanStatus=SpanStatus.OK
    error_code:str|None=None
    metadata:dict[str,Any]=field(default_factory=dict)


@dataclass
class Trace:
    trace_id:str
    spans:list[TraceSpan]=field(default_factory=list)
    events:list[TraceEvent]=field(default_factory=list)
