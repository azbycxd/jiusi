"""【生产化扩展设计，当前真实项目未实现】向量存储协议与相似度数学 Reference。"""
import math
from typing import Mapping, Protocol, Sequence


def dot_product(left, right):
    if len(left) != len(right): raise ValueError("向量维度不同")
    return sum(a*b for a,b in zip(left,right))


def l2_distance(left, right):
    if len(left) != len(right): raise ValueError("向量维度不同")
    return math.sqrt(sum((a-b)**2 for a,b in zip(left,right)))


def cosine_similarity(left, right):
    denominator = math.sqrt(dot_product(left,left))*math.sqrt(dot_product(right,right))
    return dot_product(left,right)/denominator if denominator else 0.0


class VectorStore(Protocol):
    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]],
            metadata: Sequence[Mapping]): ...
    def search(self, vector: Sequence[float], *, top_k: int, metadata_filter=None): ...
    def delete(self, ids: Sequence[str]): ...


# 向量归一化后 cosine 与 dot product 的排序可等价；未归一化 dot product 受模长影响。
