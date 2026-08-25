from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, asdict


logger = logging.getLogger("group_buy_agent.trace")


@dataclass(frozen=True)
class TraceEvent:
    trace_id: str
    session_id: str
    stage: str
    action: str
    tool_name: str | None
    tool_success: bool | None
    error_code: str | None
    duration_ms: int
    iteration_count: int
    tool_call_count: int
    retry_count: int
    model_call_count: int
    model_retry_count: int
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class TraceRecorder:
    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex
        self.events: list[TraceEvent] = []

    def record(self, *, session_id: str, stage: str, action: str, tool_name: str | None = None,
               tool_success: bool | None = None, error_code: str | None = None,
               started_at: float | None = None, iteration_count: int = 0, tool_call_count: int = 0,
               retry_count: int = 0, model_call_count: int = 0, model_retry_count: int = 0,
               model: str | None = None, input_tokens: int | None = None,
               output_tokens: int | None = None, total_tokens: int | None = None) -> None:
        elapsed = 0 if started_at is None else round((time.perf_counter() - started_at) * 1000)
        event = TraceEvent(self.trace_id, session_id, stage, action, tool_name, tool_success,
                           error_code, elapsed, iteration_count, tool_call_count, retry_count,
                           model_call_count, model_retry_count, model, input_tokens,
                           output_tokens, total_tokens)
        self.events.append(event)
        logger.info(json.dumps(asdict(event), ensure_ascii=False))
