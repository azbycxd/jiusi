"""Router 协议：决定“这是什么任务”，不决定“下一步做什么”。"""
from typing import Protocol, Sequence
from .routing_result import RoutingResult


class IntentRouter(Protocol):
    def route(self, query: str, context: object | None = None,
              candidate_skills: Sequence[object] = ()) -> RoutingResult:
        """返回结构化路由，不执行 Tool 或创建 Skill。"""
        ...
