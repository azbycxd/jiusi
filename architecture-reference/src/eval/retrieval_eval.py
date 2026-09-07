"""【B 架构重构】Retrieval Quality 与 Generation Quality 分离评测。"""
from dataclasses import dataclass
from .metrics import (hit_rate_at_k,ndcg_at_k,precision_at_k,
                      recall_at_k,reciprocal_rank)


@dataclass(frozen=True)
class RetrievalCaseResult:
    case_id:str
    passed:bool
    retrieved_ids:tuple[str,...]
    recall:float
    precision:float
    mrr:float
    hit_rate:float
    ndcg:float
    failures:tuple[str,...]=()


class RetrievalEvaluator:
    def evaluate(self,case,result):
        ids=tuple(hit.document_id for hit in result.hits)
        k=case.expected_top_k
        failures=[]
        if case.expected_empty and ids: failures.append("EXPECTED_EMPTY")
        if not case.expected_empty and not set(ids[:k])&set(case.relevant_document_ids): failures.append("NO_RELEVANT_HIT")
        if set(ids)&set(case.forbidden_document_ids): failures.append("FORBIDDEN_DOCUMENT_RETRIEVED")
        return RetrievalCaseResult(case.case_id,not failures,ids,
            recall_at_k(ids,case.relevant_document_ids,k),
            precision_at_k(ids,case.relevant_document_ids,k),
            reciprocal_rank(ids,case.relevant_document_ids),
            hit_rate_at_k(ids,case.relevant_document_ids,k),
            ndcg_at_k(ids,case.relevant_document_ids,k),tuple(failures))
