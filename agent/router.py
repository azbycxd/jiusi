from __future__ import annotations

import re
from dataclasses import dataclass

from agent.slots import SlotValidationResult, validate_out_trade_no
from agent.state import Intent


# V1 only extracts unambiguous identifier-shaped tokens that contain a digit. The
# validator itself accepts broader non-business-specific identifiers for future
# structured LLM input, so this is not an order-number format rule.
ORDER_LABEL_PATTERN = re.compile(r"(?:订单号|订单)\s*[:：#]?\s*([^\s，。！？?]+)")
ORDER_CANDIDATE_PATTERN = re.compile(r"(?<!\S)([A-Za-z0-9._-]*\d[A-Za-z0-9._-]*)(?!\S)")
ORDER_FACTS_WORDS = ("拼团", "订单", "查询", "状态", "成功", "为什么", "未成团")


@dataclass(frozen=True)
class RoutingResult:
    """Pure V1 routing output. Applying it to AgentState is the orchestrator's job."""

    normalized_query: str
    intent: Intent
    out_trade_no: SlotValidationResult
    has_out_trade_no_candidate: bool


def route(user_query: str, previous_intent: Intent = Intent.UNKNOWN) -> RoutingResult:
    """V1 deterministic router and slot extractor; it does not mutate AgentState."""
    normalized_query = user_query.strip()
    labeled_match = ORDER_LABEL_PATTERN.search(normalized_query)
    if labeled_match and any(char.isascii() for char in labeled_match.group(1)):
        candidate = labeled_match.group(1)
    else:
        match = ORDER_CANDIDATE_PATTERN.search(normalized_query)
        candidate = match.group(1) if match else None
    intent = Intent.ORDER_FACTS if (
        previous_intent is Intent.ORDER_FACTS or any(word in normalized_query for word in ORDER_FACTS_WORDS)
    ) else Intent.UNKNOWN
    return RoutingResult(
        normalized_query=normalized_query,
        intent=intent,
        out_trade_no=validate_out_trade_no(candidate),
        has_out_trade_no_candidate=candidate is not None,
    )
