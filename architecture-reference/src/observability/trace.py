"""【B 架构重构】内存 TraceRecorder；不替代 AgentState 或生产 APM。"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime,timezone
from time import perf_counter
from uuid import uuid4
from .events import SpanStatus,SpanType,Trace,TraceEvent,TraceSpan
from .sanitizer import TelemetrySanitizer


def _now(): return datetime.now(timezone.utc).isoformat()


class TraceRecorder:
    def __init__(self,sanitizer=None):
        self.sanitizer=sanitizer or TelemetrySanitizer(); self.traces={}; self.events=[]

    def _trace(self,trace_id): return self.traces.setdefault(trace_id,Trace(trace_id))

    def record_event(self,**kwargs):
        kwargs.setdefault("timestamp",_now()); kwargs["metadata"]=self.sanitizer.sanitize(kwargs.get("metadata",{}))
        event=TraceEvent(**kwargs); self.events.append(event); self._trace(event.trace_id).events.append(event); return event

    def record_model_call(self,**kwargs):
        return self.record_event(stage="MODEL_CALL",action="DECISION",**kwargs)

    def record_tool_call(self,**kwargs):
        return self.record_event(stage="TOOL_CALL",action="CALL",**kwargs)

    def record_state_transition(self,**kwargs):
        reason=kwargs.pop("reason_code",None)
        return self.record_event(stage=kwargs.pop("stage","STATE"),action="TRANSITION",
                                 error_code=reason,**kwargs)

    def start_span(self,trace_id,span_type,*,parent_span_id=None,session_id=None,
                   task_id=None,skill_name=None,metadata=None):
        kind=span_type if isinstance(span_type,SpanType) else SpanType(span_type)
        span=TraceSpan(trace_id,uuid4().hex,parent_span_id,kind,session_id,task_id,
                       skill_name,_now(),metadata=self.sanitizer.sanitize(metadata or {}))
        self._trace(trace_id).spans.append(span); return span

    def end_span(self,span,*,status=SpanStatus.OK,error_code=None,metadata=None,duration_ms=None):
        trace=self._trace(span.trace_id); index=next(i for i,item in enumerate(trace.spans) if item.span_id==span.span_id)
        ended=replace(span,end_time=_now(),duration_ms=duration_ms if duration_ms is not None else 0.0,
                      status=status,error_code=error_code,
                      metadata=self.sanitizer.sanitize({**span.metadata,**(metadata or {})}))
        trace.spans[index]=ended; return ended

    @contextmanager
    def span(self,trace_id,span_type,**kwargs):
        span=self.start_span(trace_id,span_type,**kwargs); started=perf_counter()
        try:
            yield span
        except Exception:
            self.end_span(span,status=SpanStatus.ERROR,error_code="INTERNAL_ERROR",
                          duration_ms=(perf_counter()-started)*1000)
            raise
        else:
            self.end_span(span,duration_ms=(perf_counter()-started)*1000)
