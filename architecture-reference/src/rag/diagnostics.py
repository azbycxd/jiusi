"""【B 架构重构】RAG 分段故障定位，避免把所有错误都归因于模型。"""
from dataclasses import dataclass
from enum import Enum


class RAGFailureStage(str,Enum):
    QUERY_UNDERSTANDING_FAILURE="QUERY_UNDERSTANDING_FAILURE"
    CHUNKING_FAILURE="CHUNKING_FAILURE"
    INDEXING_FAILURE="INDEXING_FAILURE"
    RETRIEVAL_FAILURE="RETRIEVAL_FAILURE"
    FILTER_FAILURE="FILTER_FAILURE"
    FUSION_FAILURE="FUSION_FAILURE"
    RERANK_FAILURE="RERANK_FAILURE"
    CONTEXT_ASSEMBLY_FAILURE="CONTEXT_ASSEMBLY_FAILURE"
    GENERATION_FAILURE="GENERATION_FAILURE"


@dataclass(frozen=True)
class RAGDiagnostic:
    stage:RAGFailureStage
    reason:str


def diagnose(*,answer_in_source,answer_in_index,answer_in_recall,
             answer_after_filter=True,answer_after_fusion=True,
             answer_after_rerank=True,answer_in_context=True,generation_correct=True):
    if not answer_in_source: return RAGDiagnostic(RAGFailureStage.CHUNKING_FAILURE,"正确答案未形成语义 Chunk")
    if not answer_in_index: return RAGDiagnostic(RAGFailureStage.INDEXING_FAILURE,"正确 Chunk 未进入索引")
    if not answer_in_recall: return RAGDiagnostic(RAGFailureStage.RETRIEVAL_FAILURE,"正确 Chunk 未进入 Top-K")
    if not answer_after_filter: return RAGDiagnostic(RAGFailureStage.FILTER_FAILURE,"正确候选被过滤")
    if not answer_after_fusion: return RAGDiagnostic(RAGFailureStage.FUSION_FAILURE,"融合阶段丢失候选")
    if not answer_after_rerank: return RAGDiagnostic(RAGFailureStage.RERANK_FAILURE,"正确候选被重排移除")
    if not answer_in_context: return RAGDiagnostic(RAGFailureStage.CONTEXT_ASSEMBLY_FAILURE,"候选未进入上下文")
    if not generation_correct: return RAGDiagnostic(RAGFailureStage.GENERATION_FAILURE,"上下文正确但生成错误")
    return None
