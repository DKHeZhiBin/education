from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from app.core.config import Settings, settings


class EmbeddingProviderError(RuntimeError):
    """中文：定义“嵌入·提供方·error”类，封装该职责相关的数据与行为。
    English: Defines the embedding provider error class and encapsulates data and behavior for that responsibility.
    """
    pass


@runtime_checkable
class EmbeddingProvider(Protocol):
    """中文：定义“嵌入·提供方”类，封装该职责相关的数据与行为。
    English: Defines the embedding provider class and encapsulates data and behavior for that responsibility.
    """

    @property
    def name(self) -> str:
        """中文：处理“name”相关操作。
        English: Handles the name operation.
        """
        ...

    @property
    def model_name(self) -> str:
        """中文：处理“模型·name”相关操作。
        English: Handles the model name operation.
        """
        ...

    @property
    def dimensions(self) -> int:
        """中文：处理“dimensions”相关操作。
        English: Handles the dimensions operation.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        ...

    def embed_query(self, text: str) -> list[float]:
        """中文：处理“embed·query”相关操作。
        English: Handles the embed query operation.
        """
        ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """中文：处理“embed·documents”相关操作。
        English: Handles the embed documents operation.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        ...

    def close(self) -> None:
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        ...


class OpenAICompatibleEmbeddingProvider:
    """中文：定义“打开·aicompatible·嵌入·提供方”类，封装该职责相关的数据与行为。
    English: Defines the open aicompatible embedding provider class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Embedding adapter for APIs implementing POST /embeddings.
    """

    name = "openai_compatible"

    def __init__(self, config: Settings = settings) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.config = config
        self._client = httpx.Client(
            base_url=config.embedding_base_url.rstrip("/"),
            headers=self._headers(config),
            timeout=config.embedding_timeout_seconds,
        )

    @property
    def model_name(self) -> str:
        """中文：处理“模型·name”相关操作。
        English: Handles the model name operation.
        """
        return self.config.embedding_model

    @property
    def dimensions(self) -> int:
        """中文：处理“dimensions”相关操作。
        English: Handles the dimensions operation.
        """
        return self.config.embedding_dimensions

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        return bool(self.config.embedding_base_url and self.model_name)

    def embed_query(self, text: str) -> list[float]:
        """中文：处理“embed·query”相关操作。
        English: Handles the embed query operation.
        """
        vectors = self._embed([text], input_type="query")
        return vectors[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """中文：处理“embed·documents”相关操作。
        English: Handles the embed documents operation.
        """
        return self._embed(texts, input_type="document")

    def _embed(self, texts: list[str], *, input_type: str) -> list[list[float]]:
        """中文：处理“embed”相关操作。
        English: Handles the embed operation.
        """
        if not self.available:
            raise EmbeddingProviderError("embedding provider is not configured")
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingProviderError("embedding input must contain non-empty text")
        try:
            response = self._client.post(
                "/embeddings",
                json={
                    "model": self.model_name,
                    "input": texts,
                    "input_type": input_type,
                },
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
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
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
        """中文：处理“关闭”相关操作。
        English: Handles the close operation.
        """
        self._client.close()

    @staticmethod
    def _headers(config: Settings) -> dict[str, str]:
        """中文：处理“headers”相关操作。
        English: Handles the headers operation.
        """
        headers = {"Content-Type": "application/json"}
        if config.embedding_api_key:
            headers["Authorization"] = f"Bearer {config.embedding_api_key}"
        return headers


def build_embedding_provider(config: Settings = settings) -> EmbeddingProvider:
    """中文：处理“构建·嵌入·提供方”相关操作。
    English: Handles the build embedding provider operation.
    """
    return OpenAICompatibleEmbeddingProvider(config)
