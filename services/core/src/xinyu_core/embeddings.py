from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from .config import AppConfig


class EmbeddingProvider(ABC):
    id = "unknown"
    model = "unknown"

    @property
    def configured(self) -> bool:
        return True

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class DisabledEmbeddingProvider(EmbeddingProvider):
    id = "disabled"

    def __init__(self, model: str) -> None:
        self.model = model

    @property
    def configured(self) -> bool:
        return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding_not_configured")


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    id = "openai-compatible"

    def __init__(self, config: AppConfig) -> None:
        if not config.embedding_base_url:
            raise ValueError("embedding_base_url is required")
        self.base_url = config.embedding_base_url.rstrip("/")
        self.model = config.embedding_model
        self.api_key = config.embedding_api_key

    async def embed(self, texts: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json={"model": self.model, "input": texts},
            )
            response.raise_for_status()
            payload = response.json()
        ordered = sorted(payload["data"], key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in ordered]


def create_embedding_provider(config: AppConfig) -> EmbeddingProvider:
    if config.embedding_base_url:
        return OpenAICompatibleEmbeddingProvider(config)
    return DisabledEmbeddingProvider(config.embedding_model)
