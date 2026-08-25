"""Deterministic validation for values that may later come from a router or LLM."""

from __future__ import annotations

import re
from dataclasses import dataclass


MAX_OUT_TRADE_NO_LENGTH = 128
ALLOWED_OUT_TRADE_NO = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class SlotValidationResult:
    value: str | None
    error_code: str | None = None

    @property
    def is_valid(self) -> bool:
        return self.value is not None and self.error_code is None


def validate_out_trade_no(value: object) -> SlotValidationResult:
    """Normalize and perform only transport-safe, format-agnostic validation.

    This is deliberately not a Java business-format validator. It accepts a broad,
    documented identifier character set and does not infer a fixed length or numeric
    order-number rule.
    """
    if value is None:
        return SlotValidationResult(None, "OUT_TRADE_NO_MISSING")
    if not isinstance(value, str):
        return SlotValidationResult(None, "OUT_TRADE_NO_INVALID_TYPE")
    normalized = value.strip()
    if not normalized:
        return SlotValidationResult(None, "OUT_TRADE_NO_MISSING")
    if len(normalized) > MAX_OUT_TRADE_NO_LENGTH:
        return SlotValidationResult(None, "OUT_TRADE_NO_INVALID_LENGTH")
    if not ALLOWED_OUT_TRADE_NO.fullmatch(normalized):
        return SlotValidationResult(None, "OUT_TRADE_NO_INVALID_CHARACTERS")
    return SlotValidationResult(normalized)
