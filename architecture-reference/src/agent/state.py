"""
当前模块解决什么问题：定义一个 Task 在 Agent Loop 中的完整工作状态。

位置：Gateway 创建请求后由 Orchestrator 创建、读取和更新；Memory 保存其快照；
ContextBuilder 只从中挑选最小必要信息给模型。

真实性：字段模型是 B 层架构重构抽象，映射当前真实项目的 AgentState、
SessionMemory、Observation、ToolResult、DiagnosisProgress 和计数器。

关键边界：State 不是聊天历史，不是长期 Memory，也不是 Trace。它只保存当前
Task 可恢复、可审计地继续执行所需的工作状态。
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

class TaskStatus(str, Enum):
    INIT='INIT'; ROUTED='ROUTED'; SKILL_ACTIVE='SKILL_ACTIVE'; REASONING='REASONING'
    ACTION='ACTION'; OBSERVING='OBSERVING'; WAITING_INPUT='WAITING_INPUT'
    COMPLETED='COMPLETED'; HANDOFF='HANDOFF'; FAILED='FAILED'

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class AgentState:
    """一个可信身份下、可恢复的单一业务 Task Working State。"""
    session_id: str
    task_id: str
    authenticated_user_id: str
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    active_skill: str | None = None
    routing_intent: str | None = None
    routing_entities: dict[str, Any] = field(default_factory=dict)
    task_status: TaskStatus = TaskStatus.INIT
    current_query: str = ''
    pending_user_query: str | None = None
    missing_information: list[str] = field(default_factory=list)
    response_message: str | None = None
    observations: list[Any] = field(default_factory=list)
    tool_results: list[Any] = field(default_factory=list)
    evidence_refs: list[Any] = field(default_factory=list)
    skill_progress: Any = None
    tool_call_history: list[str] = field(default_factory=list)
    model_call_history: list[dict[str, Any]] = field(default_factory=list)
    iteration_count: int = 0
    tool_call_count: int = 0
    model_call_count: int = 0
    model_retry_count: int = 0
    tool_retry_count: int = 0
    runtime_budget: dict[str, int] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    state_version: int = 1

    def append_tool_result(self, result: Any) -> None:
        """记录一次 ToolResult；失败也必须保留，以便 FailurePolicy 和 Trace 定位。"""
        self.tool_results.append(result)
        self.tool_call_count += 1
        self.updated_at = _now()

    def append_observation(self, observation: Any) -> None:
        """仅在成功且已完成契约验证时追加 Observation，避免把错误当业务事实。"""
        self.observations.append(observation)
        self.updated_at = _now()

    def apply_progress_evaluation(self, evaluations) -> None:
        """只存 Evaluator 结果；State 自身不判断 Evidence，也不接收 Tool dimension。"""
        if self.skill_progress is None:
            raise RuntimeError('Skill 尚未初始化 Progress')
        self.skill_progress.apply_evaluations(evaluations)
        self.updated_at = _now()

    def mark_waiting_input(self, fields: list[str]) -> None:
        """保存原问题与合法缺失实体，供同身份同 Session 后续恢复。"""
        self.pending_user_query = self.current_query
        self.missing_information = list(fields)
        self.task_status = TaskStatus.WAITING_INPUT
        self.updated_at = _now()

    def mark_completed(self, evidence_refs: list[Any]) -> None:
        """完成时保留答案所依据的 Evidence 引用，而非存储模型隐藏推理。"""
        self.evidence_refs = list(evidence_refs)
        self.task_status = TaskStatus.COMPLETED
        self.updated_at = _now()

    def mark_handoff(self, reason: str) -> None:
        """能力不足、预算耗尽或不可安全恢复时结束为 HANDOFF。"""
        self.task_status = TaskStatus.HANDOFF
        self.missing_information = [reason]
        self.updated_at = _now()

    def can_resume(self, authenticated_user_id: str) -> bool:
        """恢复前强制身份隔离；跨身份不能读取 WAITING_INPUT 状态。"""
        return self.task_status is TaskStatus.WAITING_INPUT and self.authenticated_user_id == authenticated_user_id

    def reset_for_new_task(self, query: str, task_id: str | None = None) -> None:
        """同 Session 新问题显式重置 Task 层字段，不能污染旧 Task。"""
        self.task_id = task_id or uuid4().hex
        self.current_query = query
        self.pending_user_query = None
        self.missing_information.clear(); self.observations.clear(); self.tool_results.clear()
        self.evidence_refs.clear(); self.tool_call_history.clear(); self.model_call_history.clear()
        self.skill_progress = None; self.active_skill = None; self.task_status = TaskStatus.INIT
        self.routing_intent = None; self.routing_entities.clear()
        self.response_message = None
        self.iteration_count = self.tool_call_count = self.model_call_count = 0
        self.model_retry_count = self.tool_retry_count = 0
        self.state_version += 1; self.updated_at = _now()

    def snapshot(self) -> 'AgentState':
        """返回深拷贝，避免 Memory 调用方原地修改已保存 State。"""
        return deepcopy(self)
