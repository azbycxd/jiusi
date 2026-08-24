from __future__ import annotations

import re

from agent.state import AgentState, Intent


ORDER_PATTERN = re.compile(r"(?<!\d)(\d{6,32})(?!\d)")
DIAGNOSIS_WORDS = ("拼团", "订单", "成功", "为什么", "未成团")


def route(state: AgentState, user_query: str) -> None:
    """V1 deterministic router and slot extractor; no LLM is involved."""
    state.context.user_query = user_query.strip()
    match = ORDER_PATTERN.search(user_query)
    if match:
        state.context.out_trade_no = match.group(1)
    if state.intent is Intent.ORDER_DIAGNOSIS or any(word in user_query for word in DIAGNOSIS_WORDS):
        state.context.intent = Intent.ORDER_DIAGNOSIS
