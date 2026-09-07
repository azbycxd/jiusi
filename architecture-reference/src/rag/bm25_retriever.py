"""【生产化扩展设计，当前真实项目未实现】无第三方依赖的 BM25 教学 Reference。

当前真实项目使用自定义 Lexical Retriever，不声称使用标准 BM25 库。BM25 对订单号、
活动 ID、错误码和专有名词等 lexical-heavy Query 有价值。
"""
from collections import Counter
import math
from .lexical_retriever import lexical_tokens
from .retriever import RetrievalHit, RetrievalResult


class BM25Retriever:
    """score = IDF * TF*(k1+1)/(TF+k1*(1-b+b*dl/avgdl))。"""
    def __init__(self, entries, k1=1.5, b=0.75, minimum_score=0.0):
        if k1 <= 0 or not 0 <= b <= 1:
            raise ValueError("BM25 参数超出参考范围")
        self.entries = tuple(entries)
        self.k1, self.b, self.minimum_score = k1, b, minimum_score
        self.documents = [lexical_tokens(" ".join((e.title, e.category, " ".join(e.tags), e.content)))
                          for e in self.entries]
        self.lengths = [len(tokens) for tokens in self.documents]
        self.avgdl = sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        self.df = Counter(token for doc in self.documents for token in set(doc))

    def _idf(self, token):
        count, total = self.df.get(token, 0), len(self.documents)
        return math.log(1.0 + (total-count+0.5)/(count+0.5)) if total else 0.0

    def _score(self, query_tokens, document, length):
        frequencies = Counter(document)
        terms = {}
        total = 0.0
        for token in set(query_tokens):
            tf = frequencies.get(token, 0)
            if not tf:
                continue
            normalizer = tf + self.k1 * (1-self.b+self.b*length/(self.avgdl or 1.0))
            value = self._idf(token) * tf * (self.k1+1) / normalizer
            terms[token] = value
            total += value
        return total, terms

    def search_with_scores(self, query, entries=None, top_k=3):
        if entries is not None and tuple(entries) != self.entries:
            return BM25Retriever(entries, self.k1, self.b, self.minimum_score).search_with_scores(query, top_k=top_k)
        query_tokens = lexical_tokens(query)
        ranked = []
        for entry, document, length in zip(self.entries, self.documents, self.lengths):
            score, terms = self._score(query_tokens, document, length)
            if score > self.minimum_score:
                ranked.append(RetrievalHit(entry, score, {f"term:{k}":v for k,v in terms.items()}))
        ranked.sort(key=lambda hit: (-hit.score, hit.document_id))
        hits = tuple(RetrievalHit(hit.entry, hit.score, hit.score_breakdown,
                                  {"bm25": index})
                     for index, hit in enumerate(ranked[:top_k], 1))
        return RetrievalResult(query, hits, top_k, self.minimum_score)

    def search(self, query, entries=None, top_k=3):
        return list(self.search_with_scores(query, entries, top_k))
