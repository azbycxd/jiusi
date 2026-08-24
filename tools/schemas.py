from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    kind: str
    value: str
    source: str


class ToolResult(BaseModel):
    """Business outcome, not an exception wrapper."""

    success: bool
    error_code: str | None = None
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    retryable: bool = False
    source: str

    @classmethod
    def infrastructure_failure(cls, code: str, message: str, *, retryable: bool, source: str) -> "ToolResult":
        return cls(success=False, error_code=code, message=message, retryable=retryable, source=source)
