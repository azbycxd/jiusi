from __future__ import annotations

import re
from collections import Counter
from typing import Protocol, runtime_checkable

from knowledge.contracts import KnowledgeCatalog, KnowledgeEntry, RuleSearchItem, RuleSearchResult


@runtime_checkable
class RuleRetriever(Protocol):
    """Narrow replacement seam for local lexical or future embedding retrieval."""

    def search(self, query: str) -> RuleSearchResult: ...


class LexicalRuleRetriever:
    """Deterministic dependency-free baseline for the small reviewed Chinese catalog."""

    def __init__(self, catalog: KnowledgeCatalog, *, top_k: int = 3, minimum_score: float = 0.12) -> None:
        self._catalog = catalog
        self._top_k = top_k
        self._minimum_score = minimum_score

    def search(self, query: str) -> RuleSearchResult:
        normalized_query = self._normalize(query)
        ranked = [
            (self._score(normalized_query, entry), entry)
            for entry in self._catalog.entries
        ]
        ranked.sort(key=lambda item: (-item[0], item[1].knowledge_id))
        items = [
            RuleSearchItem.from_entry(entry)
            for score, entry in ranked[: self._top_k]
            if score >= self._minimum_score
        ]
        return RuleSearchResult(catalog_version=self._catalog.version, query=query, results=items)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(re.findall(r"[\u4e00-\u9fff]+|[a-z0-9]+", value.lower()))

    @classmethod
    def _features(cls, normalized: str) -> Counter[str]:
        # Single Chinese characters are too noisy (for example, the common character
        # "么" must not make an unrelated question look like a rule match). ASCII
        # terms remain whole tokens, so an unrelated substring such as "on" in
        # "Python" cannot match an English category name.
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", normalized))
        features = Counter(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
        features.update(f"token:{token}" for token in re.findall(r"[a-z0-9]+", normalized))
        return features

    @classmethod
    def _overlap(cls, query: str, text: str) -> float:
        query_features = cls._features(query)
        text_features = cls._features(text)
        if not query_features or not text_features:
            return 0.0
        shared = sum((query_features & text_features).values())
        return shared / sum(query_features.values())

    def _score(self, query: str, entry: KnowledgeEntry) -> float:
        title = self._normalize(entry.title)
        category = self._normalize(entry.category)
        tags = [self._normalize(tag) for tag in entry.tags]
        content = self._normalize(entry.content)
        score = 2.4 * self._overlap(query, title)
        score += 1.7 * self._overlap(query, category)
        score += sum(2.0 * self._overlap(query, tag) for tag in tags)
        score += 0.8 * self._overlap(query, content)
        if query and query in title:
            score += 2.0
        if query and query in content:
            score += 0.7
        for tag in tags:
            if tag and (tag in query or query in tag):
                score += 1.5
        return score
