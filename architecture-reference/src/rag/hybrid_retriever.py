"""【生产化扩展设计，当前真实项目未实现】BM25 + Dense 的合并、去重与两种融合。"""
from collections import defaultdict
from .retriever import RetrievalHit, RetrievalResult


def _scored(retriever, query, top_k):
    if hasattr(retriever, "search_with_scores"):
        return retriever.search_with_scores(query, top_k=top_k)
    raise TypeError("Hybrid 子检索器必须返回可解释分数")


class HybridRetriever:
    def __init__(self, retrievers, weights=None, fusion="rrf", rrf_k=60):
        self.retrievers = dict(retrievers)
        self.weights = weights or {name:1.0 for name in self.retrievers}
        self.fusion, self.rrf_k = fusion, rrf_k

    def search_with_scores(self, query, entries=None, top_k=5):
        results = {name:_scored(retriever,query,max(top_k,20))
                   for name,retriever in self.retrievers.items()}
        by_id, scores, breakdown, ranks = {}, defaultdict(float), defaultdict(dict), defaultdict(dict)
        for name, result in results.items():
            maximum = max((hit.score for hit in result.hits), default=1.0) or 1.0
            for rank, hit in enumerate(result.hits,1):
                key=hit.document_id; by_id[key]=hit.entry; ranks[key][name]=rank
                if self.fusion == "weighted":
                    value=self.weights.get(name,1.0)*hit.score/maximum
                elif self.fusion == "rrf":
                    value=self.weights.get(name,1.0)/(self.rrf_k+rank)
                else: raise ValueError("未知融合方式")
                scores[key]+=value; breakdown[key][name]=value
        ordered=sorted(by_id,key=lambda key:(-scores[key],key))[:top_k]
        hits=tuple(RetrievalHit(by_id[key],scores[key],breakdown[key],ranks[key]) for key in ordered)
        return RetrievalResult(query,hits,top_k)

    def search(self, query, entries=None, top_k=5):
        return list(self.search_with_scores(query,entries,top_k))


# 原始 BM25 与 Dense 分数尺度不同，直接相加不可靠；RRF 只依赖 rank，通常更稳健。
