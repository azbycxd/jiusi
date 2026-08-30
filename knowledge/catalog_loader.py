from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from knowledge.contracts import KnowledgeCatalog


DEFAULT_CATALOG_PATH = Path(__file__).with_name("catalogs") / "group_buy_rules_v1.json"


class CatalogLoadError(ValueError):
    """The reviewed local catalog is missing, malformed, or violates its contract."""


def load_knowledge_catalog(path: Path = DEFAULT_CATALOG_PATH) -> KnowledgeCatalog:
    """Load the exact approved artifact at the local knowledge boundary."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogLoadError("Knowledge catalog could not be loaded") from error
    try:
        return KnowledgeCatalog.model_validate(raw)
    except ValidationError as error:
        raise CatalogLoadError("Knowledge catalog violates its contract") from error
