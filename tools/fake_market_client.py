from __future__ import annotations

from dataclasses import dataclass, field

from guardrails.auth_context import AuthContext
from tools.schemas import ToolResult


@dataclass
class FakeMarketClient:
    """Scripted in-process MarketClient for unit tests; it makes no HTTP calls."""

    results_by_order: dict[str, ToolResult] = field(default_factory=dict)
    calls: list[tuple[AuthContext, str]] = field(default_factory=list)

    def get_order_facts(self, auth: AuthContext, out_trade_no: str) -> ToolResult:
        self.calls.append((auth, out_trade_no))
        return self.results_by_order[out_trade_no]
