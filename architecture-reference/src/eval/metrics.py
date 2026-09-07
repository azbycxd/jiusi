"""【B 架构重构】确定性 Agent 聚合与检索指标。"""
from dataclasses import dataclass,field
import math


@dataclass
class EvalMetrics:
    values:dict[str,int]=field(default_factory=lambda:{"PASS":0,"FAIL":0,"INFRA_FAILURE":0})
    def add(self,status):
        key=getattr(status,"value",status); self.values[key]=self.values.get(key,0)+1
    @property
    def total(self): return sum(self.values.values())
    @property
    def pass_rate(self): return self.values.get("PASS",0)/self.total if self.total else 0.0


def recall_at_k(retrieved,relevant,k):
    relevant=set(relevant)
    return len(set(retrieved[:k])&relevant)/len(relevant) if relevant else 1.0


def precision_at_k(retrieved,relevant,k):
    selected=list(retrieved[:k])
    return len(set(selected)&set(relevant))/len(selected) if selected else 0.0


def hit_rate_at_k(retrieved,relevant,k):
    return float(bool(set(retrieved[:k])&set(relevant)))


def reciprocal_rank(retrieved,relevant):
    relevant=set(relevant)
    return next((1.0/index for index,item in enumerate(retrieved,1) if item in relevant),0.0)


def ndcg_at_k(retrieved,relevant,k):
    """【C 生产扩展指标】二元 relevance 的可运行 Reference。"""
    relevant=set(relevant)
    dcg=sum(1/math.log2(index+1) for index,item in enumerate(retrieved[:k],1) if item in relevant)
    ideal=sum(1/math.log2(index+1) for index in range(1,min(len(relevant),k)+1))
    return dcg/ideal if ideal else 1.0
