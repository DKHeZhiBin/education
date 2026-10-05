from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.config import Settings, settings


class EmbeddingProviderError(RuntimeError):
    pass


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    @property
    def available(self) -> bool: ...

    def embed_query(self, text: str) -> list[float]: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def check_readiness(self) -> tuple[bool, str]: ...

    def close(self) -> None: ...


class OpenAICompatibleEmbeddingProvider:
    """Embedding adapter for APIs implementing POST /embeddings."""

    name = "openai_compatible"

    def __init__(self, config: Settings = settings) -> None:
        self.config = config
        self._client = httpx.Client(
            base_url=config.embedding_base_url.rstrip("/"),
            headers=self._headers(config),
            timeout=config.embedding_timeout_seconds,
        )

    @property
    def model_name(self) -> str:
        return self.config.embedding_model

    @property
    def dimensions(self) -> int:
        return self.config.embedding_dimensions

    @property
    def available(self) -> bool:
        return bool(self.config.embedding_base_url and self.model_name)

    def embed_query(self, text: str) -> list[float]:
        vectors = self.embed_documents([text])
        return vectors[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not self.available:
            raise EmbeddingProviderError("embedding provider is not configured")
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingProviderError("embedding input must contain non-empty text")
        try:
            response = self._client.post(
                "/embeddings",
                json={"model": self.model_name, "input": texts},
            )
            response.raise_for_status()
            rows = response.json()["data"]
            ordered = sorted(rows, key=lambda row: int(row["index"]))
            vectors = [[float(value) for value in row["embedding"]] for row in ordered]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise EmbeddingProviderError("embedding request failed") from error
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("embedding response count does not match input")
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingProviderError(
                f"embedding dimension does not match configured size {self.dimensions}"
            )
        return vectors

    def check_readiness(self) -> tuple[bool, str]:
        if not self.available:
            return False, "not_configured"
        if not self.config.embedding_readiness_path:
            return True, "configuration_only"
        try:
            response = self._client.get(self.config.embedding_readiness_path)
            response.raise_for_status()
            return True, "reachable"
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.HTTPStatusError as error:
            return False, f"http_{error.response.status_code}"
        except httpx.HTTPError:
            return False, "connection_failed"

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _headers(config: Settings) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if config.embedding_api_key:
            headers["Authorization"] = f"Bearer {config.embedding_api_key}"
        return headers


def build_embedding_provider(config: Settings = settings) -> EmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(config)
