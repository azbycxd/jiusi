"""【C 生产扩展，当前未实现】固定 Rubric 的 LLM Judge 协议，不接真实模型。"""
from dataclasses import dataclass
from typing import Mapping,Protocol


@dataclass(frozen=True)
class JudgeInput:
    user_query:str
    reference_facts:tuple[str,...]
    retrieved_context:tuple[str,...]
    model_answer:str
    rubric:Mapping[str,str]


@dataclass(frozen=True)
class JudgeResult:
    score:float
    dimensions:Mapping[str,float]
    reason_summary:str


class LLMJudge(Protocol):
    def judge(self,value:JudgeInput)->JudgeResult: ...


# 生产应固定 Judge Prompt/Rubric/模型版本并使用低温设置；低分、临界、争议 Case
# 需要人工复核。风险包括 judge bias、position bias、self-preference 与 model drift。
# Correctness、Faithfulness、Relevance、Completeness、Unsupported Claim Rate 应分开；
# BLEU/ROUGE 的表面重合不足以评判开放式业务答案。
