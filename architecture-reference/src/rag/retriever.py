"""【B 架构重构】统一检索结果保留分数拆解，供 Trace 与 Eval 使用。"""
from dataclasses import dataclass, field
from typing import Mapping, Protocol
from .knowledge_entry import KnowledgeEntry


@dataclass(frozen=True)
class RetrievalHit:
    entry: KnowledgeEntry
    score: float
    score_breakdown: Mapping[str, float] = field(default_factory=dict)
    ranks: Mapping[str, int] = field(default_factory=dict)

    @property
    def document_id(self):
        return self.entry.knowledge_id


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    hits: tuple[RetrievalHit, ...]
    top_k: int
    minimum_score: float = 0.0

    def __iter__(self):
        """兼容需要 KnowledgeEntry 序列的只读 Tool。"""
        return (hit.entry for hit in self.hits)

    def __len__(self):
        return len(self.hits)


class Retriever(Protocol):
    def search_with_scores(self, query: str, entries=None, top_k=3) -> RetrievalResult: ...
