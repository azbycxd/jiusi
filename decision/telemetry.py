from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelTelemetry:
    """Safe provider metadata. Prompt, headers and response text are never telemetry."""

    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
