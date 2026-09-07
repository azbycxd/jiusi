"""不确定性决策接口；不负责权限、执行、事实校验或最终硬约束。"""
from collections import deque
from typing import Protocol
from .schemas import AgentDecision


class DecisionModel(Protocol):
    def decide(self, context) -> AgentDecision:
        """根据模型可见投影提出一个动作。"""
        ...


class ReferenceDecisionModel:
    """仅供离线示例/测试按顺序返回 Decision，不连接真实 Provider。"""
    def __init__(self, decisions):
        self._decisions = deque(decisions)
        self.contexts = []

    def decide(self, context):
        self.contexts.append(context)
        if not self._decisions:
            raise RuntimeError("ReferenceDecisionModel 没有剩余动作")
        return self._decisions.popleft()
