"""【A 当前真实实现映射】中文 bigram + ASCII token 的 Top-3 词法检索。"""
from collections import Counter
import re
import unicodedata
from .retriever import RetrievalHit, RetrievalResult


def normalize_text(text):
    text = unicodedata.normalize("NFKC", str(text)).lower()
    return " ".join(text.split())


def lexical_tokens(text):
    normalized = normalize_text(text)
    ascii_tokens = re.findall(r"[a-z0-9_\-]+", normalized)
    cjk_runs = re.findall(r"[\u4e00-\u9fff]+", normalized)
    cjk_tokens = []
    for run in cjk_runs:
        cjk_tokens.extend(run if len(run) == 1 else
                          (run[index:index+2] for index in range(len(run)-1)))
    return tuple(ascii_tokens + cjk_tokens)


class LexicalRetriever:
    """按字段权重聚合；无匹配分数不进入结果，避免无关 Query 强行 Top-K。"""
    FIELD_WEIGHTS = {"title": 4.0, "category": 2.5, "tags": 3.0, "content": 1.0}

    def __init__(self, entries=(), minimum_score=0.1):
        self.entries = tuple(entries)
        self.minimum_score = minimum_score

    def _score(self, query, entry):
        q = normalize_text(query)
        query_counts = Counter(lexical_tokens(q))
        breakdown = {}
        fields = {
            "title": normalize_text(entry.title),
            "category": normalize_text(entry.category),
            "tags": normalize_text(" ".join(entry.tags)),
            "content": normalize_text(entry.content),
        }
        for field, text in fields.items():
            counts = Counter(lexical_tokens(text))
            overlap = sum(min(count, counts[token]) for token, count in query_counts.items())
            breakdown[f"{field}_overlap"] = overlap * self.FIELD_WEIGHTS[field]
            breakdown[f"{field}_contains"] = self.FIELD_WEIGHTS[field] * 1.5 if q and q in text else 0.0
            breakdown[f"{field}_exact"] = self.FIELD_WEIGHTS[field] * 3.0 if q == text else 0.0
        return sum(breakdown.values()), breakdown

    def search_with_scores(self, query, entries=None, top_k=3):
        catalog = tuple(self.entries if entries is None else entries)
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k 必须为正整数")
        ranked = []
        for entry in catalog:
            score, breakdown = self._score(query, entry)
            if score >= self.minimum_score:
                ranked.append(RetrievalHit(entry, score, breakdown, {"lexical": 0}))
        ranked.sort(key=lambda hit: (-hit.score, hit.document_id))
        ranked = [RetrievalHit(hit.entry, hit.score, hit.score_breakdown,
                               {"lexical": index})
                  for index, hit in enumerate(ranked[:top_k], 1)]
        return RetrievalResult(query, tuple(ranked), top_k, self.minimum_score)

    def search(self, query, entries=None, top_k=3):
        """兼容现有 Rule Tool：返回模型不可见治理字段已封装的 Entry 列表。"""
        return list(self.search_with_scores(query, entries, top_k))
