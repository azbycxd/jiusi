"""【生产化扩展设计，当前真实项目未实现】少量候选的 query-document 联合重排。"""
from dataclasses import dataclass
from typing import Protocol
from .lexical_retriever import lexical_tokens
from .retriever import RetrievalHit


class Reranker(Protocol):
    def rerank(self, query, candidates, top_k=5): ...


@dataclass(frozen=True)
class RerankResult:
    hit: RetrievalHit
    relevance_score: float


class CrossEncoderReranker:
    """可注入 scorer 的 Stub；默认词交集仅用于确定性测试，不冒充 Cross Encoder。"""
    def __init__(self, scorer=None): self.scorer=scorer or self._reference_score

    @staticmethod
    def _reference_score(query, entry):
        return float(len(set(lexical_tokens(query)) & set(lexical_tokens(entry.content))))

    def rerank(self, query, candidates, top_k=5):
        values=[RerankResult(hit,self.scorer(query,hit.entry)) for hit in candidates]
        values.sort(key=lambda item:(-item.relevance_score,item.hit.document_id))
        return tuple(values[:top_k])


# 生产示例链路可 Recall Top-20 → Rerank → Top-5；数字不是当前真实参数。
