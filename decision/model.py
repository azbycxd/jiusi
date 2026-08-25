from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from decision.schemas import DecisionContext


class DecisionModel(Protocol):
    """Vendor-neutral adapter protocol. Implementations return raw structured output."""

    def decide(self, context: DecisionContext) -> object: ...


class FakeDecisionModel:
    """Deterministic test-only model; it neither calls a network nor mimics production AI."""

    def __init__(self, responses: Sequence[object]) -> None:
        self._responses = list(responses)
        self.contexts: list[DecisionContext] = []

    def decide(self, context: DecisionContext) -> object:
        self.contexts.append(context.model_copy(deep=True))
        if not self._responses:
            raise RuntimeError("FakeDecisionModel has no scripted response")
        return self._responses.pop(0)
