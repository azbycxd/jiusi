"""【生产化扩展设计，当前真实项目未实现】Query Rewrite/Multi-Query/HyDE 契约。"""
from dataclasses import dataclass
import re
from typing import Protocol


@dataclass(frozen=True)
class QueryRewriteResult:
    original_query: str
    rewritten_query: str
    extracted_entities: dict[str, str]
    constraints: tuple[str, ...] = ()


class QueryRewriteModel(Protocol):
    def rewrite(self, query: str) -> str: ...


def extract_protected_entities(query):
    patterns = {
        "activityId": r"(?:活动|activity)\s*[:：#]?\s*(\d+)",
        "outTradeNo": r"(?:订单|订单号|outTradeNo)\s*[:：#]?\s*([A-Za-z0-9_-]+)",
        "status_code": r"\b[A-Z][A-Z0-9_]{2,}\b",
    }
    return {name:match.group(1 if match.lastindex else 0)
            for name,pattern in patterns.items()
            if (match:=re.search(pattern,query,re.I if name!="status_code" else 0))}


class QueryRewriter:
    def __init__(self, model: QueryRewriteModel | None = None): self.model=model

    def rewrite(self, query):
        entities=extract_protected_entities(query)
        rewritten=self.model.rewrite(query) if self.model else " ".join(query.split())
        for value in entities.values():
            if value not in rewritten:
                rewritten=f"{rewritten} {value}"
        return QueryRewriteResult(query,rewritten,entities,
                                  ("preserve_identifiers","no_identity_injection"))

    def multi_query(self, query, variants=()):
        """一问多表达后应 merge/dedup；精确 ID 问题不宜过度改写。"""
        results=[self.rewrite(query)]
        results.extend(self.rewrite(item) for item in variants if item != query)
        unique={item.rewritten_query:item for item in results}
        return tuple(unique.values())


class HyDEGenerator(Protocol):
    """先生成假设文档再 embedding；不适合依赖精确 ID 的 Query。"""
    def hypothetical_document(self, query: str) -> str: ...
