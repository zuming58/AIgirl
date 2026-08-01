from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    configured = os.getenv("XINYU_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Xinyu"
    return Path.home() / ".xinyu"


@dataclass(frozen=True, slots=True)
class AppConfig:
    data_dir: Path
    database_path: Path
    auth_token: str | None = None
    llm_base_url: str | None = None
    llm_model: str = "local-companion"
    llm_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_api_key: str | None = None
    speech_realtime_url: str | None = None
    app_version: str = "0.1.0"

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = _default_data_dir()
        return cls(
            data_dir=data_dir,
            database_path=data_dir / "xinyu.db",
            auth_token=os.getenv("XINYU_AUTH_TOKEN") or None,
            llm_base_url=os.getenv("XINYU_LLM_BASE_URL") or None,
            llm_model=os.getenv("XINYU_LLM_MODEL", "local-companion"),
            llm_api_key=os.getenv("XINYU_LLM_API_KEY") or None,
            embedding_base_url=os.getenv("XINYU_EMBEDDING_BASE_URL") or None,
            embedding_model=os.getenv(
                "XINYU_EMBEDDING_MODEL",
                "BAAI/bge-small-zh-v1.5",
            ),
            embedding_api_key=os.getenv("XINYU_EMBEDDING_API_KEY") or None,
            speech_realtime_url=os.getenv("XINYU_SPEECH_REALTIME_URL") or None,
        )
