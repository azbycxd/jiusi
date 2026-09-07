"""【生产化扩展设计，当前真实项目未实现】长期记忆接口。

可保存稳定偏好、历史诊断摘要和问题线索，不保存凭证或不可撤销的用户画像。
昨天的订单状态/资格不可作为今天事实：必须重新调用 Java Facts。
user_scope 隔离由实现方强制，TTL/隐私删除必须覆盖索引、缓存与副本。
下面仅定义协议，不提供 Redis/数据库实现，也不连接外部存储。
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol


class MemoryType(str, Enum):
    """只允许非权威历史摘要，避免长期缓存冒充实时事实。"""

    PREFERENCE = "PREFERENCE"
    DIAGNOSIS_SUMMARY = "DIAGNOSIS_SUMMARY"
    ISSUE_CLUE = "ISSUE_CLUE"


@dataclass(frozen=True)
class MemoryEntry:
    """内容写入前需要脱敏、来源绑定、过期和用户授权检查。"""

    memory_id: str
    user_scope: str
    memory_type: MemoryType
    content: str
    created_at: datetime
    expires_at: datetime | None
    source_task_id: str


class LongTermMemory(Protocol):
    """未来实现必须以调用方可信 scope 校验每个方法，禁止信任条目自报身份。"""

    def write(self, user_scope: str, entry: MemoryEntry) -> None:
        """写入治理后的摘要，验证 entry 的 scope 与调用方一致。"""
        ...

    def retrieve(self, user_scope: str, query: str, limit: int = 5) -> list[MemoryEntry]:
        """仅检索未过期条目，输出仍标为历史线索。"""
        ...

    def delete(self, user_scope: str, memory_id: str) -> bool:
        """删除当前用户条目与关联索引，支持隐私撤回。"""
        ...

    def expire(self, now: datetime) -> int:
        """由后台可信作业执行 TTL 到期清理，不暴露给模型。"""
        ...

    def list(self, user_scope: str) -> list[MemoryEntry]:
        """给用户或管理面展示本人的可删除记忆清单。"""
        ...
