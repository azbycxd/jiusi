from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class KnowledgeEntry(BaseModel):
    """Governed catalog entry. Source provenance remains local to the catalog boundary."""

    model_config = ConfigDict(extra="forbid")

    knowledge_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_level: Literal["LEVEL_1", "LEVEL_2", "LEVEL_3"]
    source_files: list[str] = Field(min_length=1)
    source_symbols: list[str] = Field(min_length=1)
    version: str = Field(min_length=1)
    tags: list[str] = Field(min_length=1)
    requires_realtime_facts: bool

    @field_validator("knowledge_id", "title", "category", "content", "source_type", "version")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required text must not be blank")
        return normalized

    @field_validator("source_files", "source_symbols", "tags")
    @classmethod
    def governed_lists_must_not_contain_blank_values(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if not normalized or any(not value for value in normalized):
            raise ValueError("governed list values must not be blank")
        return normalized


class KnowledgeCatalog(BaseModel):
    """Strict input contract for an approved, versioned rule catalog."""

    model_config = ConfigDict(extra="forbid")

    catalog: str = Field(min_length=1)
    version: str = Field(min_length=1)
    generated_from: str = Field(min_length=1)
    review_date: str = Field(min_length=1)
    entry_count: int = Field(ge=0)
    entries: list[KnowledgeEntry]

    @model_validator(mode="after")
    def entry_count_and_ids_must_match(self) -> "KnowledgeCatalog":
        if self.entry_count != len(self.entries):
            raise ValueError("entry_count must equal len(entries)")
        ids = [entry.knowledge_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("knowledge_id values must be unique")
        return self

    @field_validator("catalog", "version", "generated_from", "review_date")
    @classmethod
    def catalog_text_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("catalog text must not be blank")
        return normalized


class RuleSearchItem(BaseModel):
    """The small, model-visible projection of a governed catalog entry."""

    model_config = ConfigDict(extra="forbid")

    knowledge_id: str
    title: str
    category: str
    content: str
    source_level: Literal["LEVEL_1", "LEVEL_2", "LEVEL_3"]
    requires_realtime_facts: bool

    @classmethod
    def from_entry(cls, entry: KnowledgeEntry) -> "RuleSearchItem":
        return cls(
            knowledge_id=entry.knowledge_id,
            title=entry.title,
            category=entry.category,
            content=entry.content,
            source_level=entry.source_level,
            requires_realtime_facts=entry.requires_realtime_facts,
        )


class RuleSearchResult(BaseModel):
    """Normalized successful lookup result; empty results are a valid outcome."""

    model_config = ConfigDict(extra="forbid")

    catalog_version: str
    query: str
    results: list[RuleSearchItem]
