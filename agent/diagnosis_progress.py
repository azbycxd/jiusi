"""Minimal, auditable completion state for open diagnostic requests."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


_REASON_MARKERS = ("为什么", "为何", "原因", "why", "reason")
_FAILURE_MARKERS = ("参加不了", "不能", "无法", "失败", "cannot", "can't", "failed", "unable")


class DiagnosisProgress(BaseModel):
    """Only the current diagnostic goal and its independently checkable dimensions."""

    goal: str = Field(min_length=1, max_length=2000)
    required_dimensions: tuple[str, ...] = ()
    checked_dimensions: tuple[str, ...] = ()
    remaining_dimensions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def dimensions_are_consistent(self) -> "DiagnosisProgress":
        required = tuple(dict.fromkeys(self.required_dimensions))
        checked = tuple(dict.fromkeys(self.checked_dimensions))
        if required != self.required_dimensions or checked != self.checked_dimensions:
            raise ValueError("Diagnosis dimensions must be unique and ordered")
        if any(dimension not in required for dimension in checked):
            raise ValueError("Checked diagnosis dimensions must be required")
        expected_remaining = tuple(dimension for dimension in required if dimension not in checked)
        if self.remaining_dimensions != expected_remaining:
            raise ValueError("Remaining diagnosis dimensions must match required minus checked")
        return self

    @classmethod
    def for_open_diagnosis(
        cls, user_query: str, available_dimensions: tuple[str, ...]
    ) -> "DiagnosisProgress | None":
        normalized = user_query.casefold()
        if not (
            any(marker.casefold() in normalized for marker in _REASON_MARKERS)
            and any(marker.casefold() in normalized for marker in _FAILURE_MARKERS)
        ):
            return None
        dimensions = tuple(dict.fromkeys(available_dimensions))
        if not dimensions:
            return None
        return cls(
            goal=user_query,
            required_dimensions=dimensions,
            remaining_dimensions=dimensions,
        )

    @property
    def is_complete(self) -> bool:
        return not self.remaining_dimensions

    def mark_checked(self, dimension: str | None) -> "DiagnosisProgress":
        if dimension is None or dimension not in self.required_dimensions or dimension in self.checked_dimensions:
            return self
        checked = (*self.checked_dimensions, dimension)
        return self.model_copy(
            update={
                "checked_dimensions": checked,
                "remaining_dimensions": tuple(
                    item for item in self.required_dimensions if item not in checked
                ),
            }
        )
