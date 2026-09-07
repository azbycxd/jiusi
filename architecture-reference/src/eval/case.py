"""【B 架构重构】Agent 与 Retrieval 的可复现 Eval Case。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    case_id:str
    category:str
    query:str
    expected_action:str
    required_tools:tuple[str,...]=()
    forbidden_tools:tuple[str,...]=()
    required_evidence:tuple[str,...]=()
    max_tool_calls:int=5


@dataclass(frozen=True)
class RetrievalEvalCase:
    case_id:str
    query:str
    relevant_document_ids:frozenset[str]
    forbidden_document_ids:frozenset[str]=frozenset()
    expected_top_k:int=3
    expected_empty:bool=False
