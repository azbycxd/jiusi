from __future__ import annotations

import os
from pathlib import Path


SUPPORTED_ENV_KEYS = frozenset(
    {
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_TIMEOUT",
        "JAVA_MARKET_BASE_URL",
        "JAVA_MARKET_ENABLE_DEV_AUTH_HEADER",
    }
)


def load_project_env(env_path: Path | None = None) -> None:
    """Load supported project-root `.env` values without overriding process env.

    This deliberately tiny parser covers ordinary `KEY=value` local-development
    files. It does not log values and never expands variables or executes content.
    """
    path = env_path or Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if key not in SUPPORTED_ENV_KEYS or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value
