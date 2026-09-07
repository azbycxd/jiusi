"""【A 当前真实实现映射】一条人工治理 Rule Entry 就是一个语义原子 Chunk。"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class KnowledgeEntry:
    """模型可见业务知识与内部治理元数据严格分开。"""
    knowledge_id: str
    title: str
    content: str
    category: str = "general"
    tags: tuple[str, ...] = ()
    source_level: str = "governed_rule"
    requires_realtime_facts: bool = False
    version: str = "v1"
    updated_at: str | None = None
    internal_metadata: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        if not all(isinstance(value, str) and value.strip()
                   for value in (self.knowledge_id, self.title, self.content, self.category)):
            raise ValueError("知识条目关键字段不能为空")

    @property
    def entry_id(self):
        """兼容早期 Reference Tool 命名。"""
        return self.knowledge_id

    def model_visible(self):
        """source_files/source_symbols 等治理路径不进入模型 Context。"""
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "category": self.category,
            "content": self.content,
            "requires_realtime_facts": self.requires_realtime_facts,
        }

    def governance_view(self):
        return {"version": self.version, "updated_at": self.updated_at,
                "source_level": self.source_level, **dict(self.internal_metadata)}
