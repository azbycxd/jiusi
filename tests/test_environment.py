from __future__ import annotations

import os

from config.environment import SUPPORTED_ENV_KEYS, load_project_env


def test_project_env_loads_only_supported_keys_and_process_env_wins(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_API_KEY=local-development-placeholder-not-a-secret\n"
        "LLM_MODEL=local-model\n"
        "LLM_BASE_URL='https://llm.example/v1'\n"
        "LLM_TIMEOUT=12\n"
        "JAVA_MARKET_BASE_URL=http://127.0.0.1:8091\n"
        "JAVA_MARKET_ENABLE_DEV_AUTH_HEADER=true\n"
        "UNSUPPORTED_VALUE=must-not-load\n",
        encoding="utf-8",
    )
    for key in SUPPORTED_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("LLM_MODEL", "process-model")

    load_project_env(env_path)

    assert os.environ["LLM_MODEL"] == "process-model"
    assert os.environ["LLM_API_KEY"] == "local-development-placeholder-not-a-secret"
    assert os.environ["LLM_BASE_URL"] == "https://llm.example/v1"
    assert os.environ["JAVA_MARKET_ENABLE_DEV_AUTH_HEADER"] == "true"
    assert "UNSUPPORTED_VALUE" not in os.environ
