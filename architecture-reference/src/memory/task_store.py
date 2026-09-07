"""B 层多任务内存参考，不是当前真实项目已部署能力。

WAITING_INPUT 时明确切题：暂停旧 Task，新 Task 拥有独立 State，再切回旧 Task。
Router 是否识别切题不由存储决定；调用方显式调用 switch_task/pause_task。
active_task_id 按 Session 和身份隔离，保存/读取皆为深拷贝。
Reference 是单进程存储；事务、Redis、TTL 与分布式锁属于 C 层扩展。
"""
from copy import deepcopy
from uuid import uuid4
from ..agent.state import AgentState, TaskStatus


class TaskStore:
    """每个 Session/身份有多个 task_id，但至多一个 active_task_id。"""

    def __init__(self):
        self._tasks = {}
        self.active_task_id = {}
        self._paused = set()

    @staticmethod
    def _scope(session_id, identity):
        """身份是作用域必要部分，不允许无身份读取任务列表。"""
        if not session_id or not identity:
            raise PermissionError("缺少会话身份")
        return (session_id, identity)

    def create_task(self, session_id, identity, query, *, task_id=None):
        """创建并激活新 Task，旧任务只暂停不覆盖。"""
        scope = self._scope(session_id, identity)
        identifier = task_id or uuid4().hex
        key = (*scope, identifier)
        if key in self._tasks:
            raise ValueError("Task 已存在")
        active = self.active_task_id.get(scope)
        if active:
            self.pause_task(session_id, identity, active)
        state = AgentState(session_id, identifier, identity, current_query=query)
        self._tasks[key] = deepcopy(state)
        self.set_active_task(session_id, identity, identifier)
        return deepcopy(state)

    def import_state(self, state, *, active=False):
        """编排层切题时保存现有快照；这是 Batch 3A 唯一必要接线入口。"""
        scope = self._scope(state.session_id, state.authenticated_user_id)
        key = (*scope, state.task_id)
        self._tasks[key] = deepcopy(state)
        if active:
            self.set_active_task(state.session_id, state.authenticated_user_id, state.task_id)
        else:
            self._paused.add(key)
        return deepcopy(state)

    def get_task(self, session_id, identity, task_id):
        """未知/跨身份任务不返回数据。"""
        key = (*self._scope(session_id, identity), task_id)
        return deepcopy(self._tasks.get(key))

    def update_task(self, state):
        """用已读取的版本更新，防止陈旧客户端覆盖工作状态。"""
        key = (*self._scope(state.session_id, state.authenticated_user_id), state.task_id)
        existing = self._tasks.get(key)
        if existing is None or existing.state_version != state.state_version:
            raise ValueError("TASK_VERSION_CONFLICT")
        saved = deepcopy(state)
        saved.state_version += 1
        self._tasks[key] = saved
        return deepcopy(saved)

    def pause_task(self, session_id, identity, task_id):
        """暂停只是存储调度标记；保留 WAITING_INPUT 原状态和缺失字段。"""
        scope = self._scope(session_id, identity)
        if (*scope, task_id) not in self._tasks:
            raise KeyError("Task 不存在")
        self._paused.add((*scope, task_id))
        if self.active_task_id.get(scope) == task_id:
            del self.active_task_id[scope]

    def resume_task(self, session_id, identity, task_id):
        """恢复调度权；具体补参由 Session/编排层处理。"""
        self.switch_task(session_id, identity, task_id)
        return self.get_task(session_id, identity, task_id)

    def switch_task(self, session_id, identity, task_id):
        """先校验目标，再暂停旧任务，避免切换失败丢失 active 指针。"""
        scope = self._scope(session_id, identity)
        target = self.get_task(session_id, identity, task_id)
        if target is None or target.task_status in {TaskStatus.COMPLETED, TaskStatus.HANDOFF, TaskStatus.FAILED}:
            raise ValueError("目标任务不存在或已结束")
        old = self.active_task_id.get(scope)
        if old and old != task_id:
            self.pause_task(session_id, identity, old)
        self.active_task_id[scope] = task_id
        self._paused.discard((*scope, task_id))

    def complete_task(self, session_id, identity, task_id):
        """结束后解除活跃指针，但保留快照供审计。"""
        state = self.get_task(session_id, identity, task_id)
        if state is None:
            raise KeyError("Task 不存在")
        state.mark_completed(state.evidence_refs)
        saved = self.update_task(state)
        scope = self._scope(session_id, identity)
        if self.active_task_id.get(scope) == task_id:
            del self.active_task_id[scope]
        self._paused.discard((*scope, task_id))
        return saved

    def list_session_tasks(self, session_id, identity):
        """只列指定可信身份的任务副本。"""
        scope = self._scope(session_id, identity)
        return [deepcopy(value) for key, value in self._tasks.items() if key[:2] == scope]

    def set_active_task(self, session_id, identity, task_id):
        """显式入口复用切换约束，禁止指向不存在任务。"""
        self.switch_task(session_id, identity, task_id)

    def get_active_task(self, session_id, identity):
        """返回当前活跃任务或 None，不泄漏其他身份指针。"""
        task_id = self.active_task_id.get(self._scope(session_id, identity))
        return self.get_task(session_id, identity, task_id) if task_id else None
