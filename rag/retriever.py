from typing import Protocol


class SupportKnowledgeRetriever(Protocol):
    """Future FAQ/rule lookup only; it must not determine live order facts."""

    def retrieve(self, query: str, limit: int = 3) -> list[str]: ...
