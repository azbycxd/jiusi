"""A 层 SessionMemory 行为映射，带 B 层版本比较的内存 Reference。

保存当前未完成 Task 的 Working State，不保存完整聊天历史。
键同时包括 session 和可信身份，禁止跨身份读取、删除、恢复另一人的状态。
save/load 都深拷贝；版本用于防止过期快照覆盖，本实现没有分布式并发保证。
生产 Redis Checkpoint、TTL、锁需要单独设计，本批不实现。
"""
from copy import deepcopy
from uuid import uuid4
from ..agent.state import AgentState, TaskStatus


class SessionMemory:
    """同一 Session/身份保存一个当前 Task；多任务交给 TaskStore。"""

    def __init__(self):
        self._states = {}

    def _key(self, session_id, identity):
        """拒绝无身份访问，不从模型 body 获取身份。"""
        if not session_id or not isinstance(identity, str) or not identity:
            raise PermissionError("缺少可信会话身份")
        return (session_id, identity)

    def save(self, state, *, expected_version=None):
        """比较后保存快照并返回新版本；第一次创建 expected_version 应为 0。"""
        key = self._key(state.session_id, state.authenticated_user_id)
        previous = self._states.get(key)
        current = previous.state_version if previous else 0
        if expected_version is not None and current != expected_version:
            raise ValueError("STATE_VERSION_CONFLICT")
        if previous is not None and expected_version is None and state.state_version != current:
            raise ValueError("STATE_VERSION_CONFLICT")
        saved = deepcopy(state)
        saved.state_version = current + 1
        self._states[key] = saved
        return deepcopy(saved)

    def load(self, session_id, authenticated_user_id):
        """返回脱离内部存储的副本；另一个身份只得到 None。"""
        key = self._key(session_id, authenticated_user_id)
        return deepcopy(self._states.get(key))

    def exists(self, session_id, authenticated_user_id):
        """判断当前身份是否拥有该 Session 的快照。"""
        return self._key(session_id, authenticated_user_id) in self._states

    def delete(self, session_id, authenticated_user_id):
        """仅删除当前身份作用域，不删除其它身份的同名 Session。"""
        key = self._key(session_id, authenticated_user_id)
        return self._states.pop(key, None) is not None

    def resume(self, session_id, authenticated_user_id, message):
        """只恢复 WAITING_INPUT；拼接原目标与补充实体且保留旧 Observation。"""
        state = self.load(session_id, authenticated_user_id)
        if state is None or not state.can_resume(authenticated_user_id):
            raise ValueError("当前任务不能恢复")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("补充信息不能为空")
        original = state.pending_user_query or state.current_query
        state.current_query = f"{original}\n用户补充信息：{message.strip()}"
        state.pending_user_query = None
        state.missing_information = []
        state.task_status = TaskStatus.REASONING
        return self.save(state, expected_version=state.state_version)

    def load_or_create(self, request):
        """兼容前批入口；跨身份/终态新建，待输入状态显式恢复。"""
        state = self.load(request.session_id, request.authenticated_user_id)
        if state is not None and state.can_resume(request.authenticated_user_id):
            return self.resume(request.session_id, request.authenticated_user_id, request.message)
        if state is not None and state.task_status not in {
            TaskStatus.COMPLETED, TaskStatus.HANDOFF, TaskStatus.FAILED
        }:
            return state
        new_state = AgentState(request.session_id, uuid4().hex,
                               request.authenticated_user_id, current_query=request.message)
        return self.save(new_state, expected_version=state.state_version if state else 0)
