from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

import httpx

from app.core.config import settings


logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    """中文：定义“llmprovider”类，封装该职责相关的数据与行为。
    English: Defines the llmprovider class and encapsulates data and behavior for that responsibility.
    """

    @property
    def provider_id(self) -> str:
        """中文：处理“提供方·id”相关操作。
        English: Handles the provider id operation.
        """
        ...

    @property
    def model_name(self) -> str:
        """中文：处理“模型·name”相关操作。
        English: Handles the model name operation.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        ...

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        """中文：处理“complete·json”相关操作。
        English: Handles the complete json operation.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        ...


@dataclass(frozen=True)
class LLMModelOption:
    """中文：定义“llmmodel·option”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel option class and encapsulates data and behavior for that responsibility.
    """
    id: str
    provider: str
    model: str
    display_name: str
    available: bool
    is_default: bool = False


class LLMModelNotFound(LookupError):
    """中文：定义“llmmodel·not·found”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel not found class and encapsulates data and behavior for that responsibility.
    """
    pass


class LLMModelUnavailable(RuntimeError):
    """中文：定义“llmmodel·unavailable”类，封装该职责相关的数据与行为。
    English: Defines the llmmodel unavailable class and encapsulates data and behavior for that responsibility.
    """
    pass


class OpenAICompatibleProvider:
    """中文：定义“打开·aicompatible·提供方”类，封装该职责相关的数据与行为。
    English: Defines the open aicompatible provider class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    OpenAI Chat Completions adapter used by DeepSeek, Gemini and future providers.
    """

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        api_key: str,
        model_name: str,
        timeout_seconds: float,
        readiness_path: str = "/models",
        temperature: float = 0.2,
        max_output_tokens: int | None = None,
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self._provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.readiness_path = readiness_path
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

    @property
    def provider_id(self) -> str:
        """中文：处理“提供方·id”相关操作。
        English: Handles the provider id operation.
        """
        return self._provider_id

    @property
    def model_name(self) -> str:
        """中文：处理“模型·name”相关操作。
        English: Handles the model name operation.
        """
        return self._model_name

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        return bool(self.base_url and self.api_key and self.model_name)

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        """中文：处理“complete·json”相关操作。
        English: Handles the complete json operation.
        """
        if not self.available:
            return None
        payload: dict[str, Any] = {
            "model": self.model_name,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self.max_output_tokens is not None:
            payload["max_tokens"] = self.max_output_tokens
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            try:
                return self._parse_json(content)
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                choice = response.json().get("choices", [{}])[0]
                logger.warning(
                    "LLM JSON response could not be parsed (finish_reason=%s, content_length=%s, error=%s)",
                    choice.get("finish_reason"),
                    len(content) if isinstance(content, str) else 0,
                    type(error).__name__,
                    extra={
                        "event": "llm_json_parse_failed",
                        "log_provider": self.provider_id,
                        "log_model": self.model_name,
                        "log_finish_reason": choice.get("finish_reason"),
                        "log_content_length": len(content) if isinstance(content, str) else 0,
                        "log_error_type": type(error).__name__,
                    },
                )
                return None
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            logger.warning(
                "LLM request failed",
                extra={
                    "event": "llm_request_failed",
                    "log_provider": self.provider_id,
                    "log_model": self.model_name,
                    "log_error_type": type(error).__name__,
                },
            )
            return None

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        if not self.available:
            return False, "not_configured"
        if not self.readiness_path:
            return True, "configuration_only"
        try:
            response = httpx.get(
                f"{self.base_url}{self.readiness_path}",
                headers=self._headers(),
                timeout=settings.readiness_timeout_seconds,
            )
            response.raise_for_status()
            return True, "reachable"
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.HTTPStatusError as error:
            return False, f"http_{error.response.status_code}"
        except httpx.HTTPError:
            return False, "connection_failed"

    def _headers(self) -> dict[str, str]:
        """中文：处理“headers”相关操作。
        English: Handles the headers operation.
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        """中文：处理“解析·json”相关操作。
        English: Handles the parse json operation.
        """
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        candidate = fenced.group(1) if fenced else content.strip()
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Agent output must be a JSON object")
        return parsed


class DisabledLLMProvider:
    """中文：定义“disabled·llmprovider”类，封装该职责相关的数据与行为。
    English: Defines the disabled llmprovider class and encapsulates data and behavior for that responsibility.
    """
    available = False

    def __init__(
        self,
        provider_id: str = "disabled",
        model_name: str = "disabled",
    ) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.provider_id = provider_id
        self.model_name = model_name

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        """中文：处理“complete·json”相关操作。
        English: Handles the complete json operation.
        """
        return None

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        return False, "not_configured"


class LLMProviderRegistry:
    """中文：定义“llmprovider·registry”类，封装该职责相关的数据与行为。
    English: Defines the llmprovider registry class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Allowlisted model catalog. Credentials stay in server configuration.
    """

    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self._providers: dict[str, LLMProvider] = {}
        self.default_model_id: str | None = None

    def register(self, provider: LLMProvider, *, default: bool = False) -> str:
        """中文：处理“register”相关操作。
        English: Handles the register operation.
        """
        model_id = self.model_id(provider.provider_id, provider.model_name)
        if model_id in self._providers:
            raise ValueError(f"LLM model is already registered: {model_id}")
        self._providers[model_id] = provider
        if default or self.default_model_id is None:
            self.default_model_id = model_id
        return model_id

    def configure_default(self, model_id: str) -> None:
        """中文：处理“configure·default”相关操作。
        English: Handles the configure default operation.
        """
        if model_id not in self._providers:
            raise LLMModelNotFound(f"default LLM model is not registered: {model_id}")
        self.default_model_id = model_id

    def list_models(self) -> list[LLMModelOption]:
        """中文：处理“列出·models”相关操作。
        English: Handles the list models operation.
        """
        return [
            LLMModelOption(
                id=model_id,
                provider=provider.provider_id,
                model=provider.model_name,
                display_name=f"{provider.provider_id.title()} · {provider.model_name}",
                available=provider.available,
                is_default=model_id == self.default_model_id,
            )
            for model_id, provider in self._providers.items()
        ]

    def resolve(self, model_id: str | None, *, require_available: bool = True) -> LLMProvider:
        """中文：处理“解析”相关操作。
        English: Handles the resolve operation.
        """
        selected_id = model_id or self.default_model_id
        if selected_id is None:
            if require_available:
                raise LLMModelUnavailable("no LLM model is configured")
            return DisabledLLMProvider()
        provider = self._providers.get(selected_id)
        if provider is None:
            if not require_available:
                provider_id, separator, model_name = selected_id.partition("/")
                return DisabledLLMProvider(
                    provider_id if separator else "disabled",
                    model_name if separator else selected_id,
                )
            raise LLMModelNotFound(f"LLM model is not registered: {selected_id}")
        if require_available and not provider.available:
            raise LLMModelUnavailable(f"LLM model is not configured: {selected_id}")
        return provider

    def resolve_provider_model(
        self,
        provider_id: str,
        model_name: str,
        *,
        require_available: bool = True,
    ) -> LLMProvider:
        """中文：处理“解析·提供方·模型”相关操作。
        English: Handles the resolve provider model operation.
        """
        return self.resolve(
            self.model_id(provider_id, model_name),
            require_available=require_available,
        )

    @staticmethod
    def model_id(provider_id: str, model_name: str) -> str:
        """中文：处理“模型·id”相关操作。
        English: Handles the model id operation.
        """
        return f"{provider_id.strip().lower()}/{model_name.strip()}"


class RoutingLLMProvider:
    """中文：定义“routing·llmprovider”类，封装该职责相关的数据与行为。
    English: Defines the routing llmprovider class and encapsulates data and behavior for that responsibility.

    原有说明 / Existing notes:
    Context-local router so shared Agents remain safe across concurrent sessions.
    """

    def __init__(self, registry: LLMProviderRegistry) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.registry = registry
        self._selected_model: ContextVar[str | None] = ContextVar(
            "selected_llm_model", default=None
        )

    @contextmanager
    def use_model(
        self,
        model_id: str | None,
        *,
        require_available: bool = True,
    ) -> Iterator[LLMProvider]:
        """中文：处理“use·模型”相关操作。
        English: Handles the use model operation.
        """
        provider = self.registry.resolve(
            model_id, require_available=require_available
        )
        token = self._selected_model.set(
            self.registry.model_id(provider.provider_id, provider.model_name)
        )
        try:
            yield provider
        finally:
            self._selected_model.reset(token)

    @contextmanager
    def use_provider_model(
        self, provider_id: str, model_name: str
    ) -> Iterator[LLMProvider]:
        """中文：处理“use·提供方·模型”相关操作。
        English: Handles the use provider model operation.
        """
        model_id = self.registry.model_id(provider_id, model_name)
        with self.use_model(model_id) as provider:
            yield provider

    def current(self, *, require_available: bool = False) -> LLMProvider:
        """中文：处理“current”相关操作。
        English: Handles the current operation.
        """
        return self.registry.resolve(
            self._selected_model.get(),
            require_available=require_available,
        )

    @property
    def provider_id(self) -> str:
        """中文：处理“提供方·id”相关操作。
        English: Handles the provider id operation.
        """
        return self.current().provider_id

    @property
    def model_name(self) -> str:
        """中文：处理“模型·name”相关操作。
        English: Handles the model name operation.
        """
        return self.current().model_name

    @property
    def available(self) -> bool:
        """中文：处理“available”相关操作。
        English: Handles the available operation.
        """
        return self.current().available

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        """中文：处理“complete·json”相关操作。
        English: Handles the complete json operation.
        """
        return self.current().complete_json(system, user)

    def check_readiness(self) -> tuple[bool, str]:
        """中文：处理“检查·就绪状态”相关操作。
        English: Handles the check readiness operation.
        """
        return self.current().check_readiness()


def _csv(value: str) -> list[str]:
    """中文：处理“csv”相关操作。
    English: Handles the csv operation.
    """
    return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def build_llm_registry() -> LLMProviderRegistry:
    """中文：处理“构建·llm·registry”相关操作。
    English: Handles the build llm registry operation.
    """
    registry = LLMProviderRegistry()
    for model in _csv(settings.deepseek_models):
        registry.register(OpenAICompatibleProvider(
            provider_id="deepseek",
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
            model_name=model,
            timeout_seconds=settings.llm_timeout_seconds,
            readiness_path=settings.llm_readiness_path,
            max_output_tokens=settings.llm_max_output_tokens,
        ))
    for model in _csv(settings.gemini_models):
        registry.register(OpenAICompatibleProvider(
            provider_id="gemini",
            base_url=settings.gemini_base_url,
            api_key=settings.gemini_api_key,
            model_name=model,
            timeout_seconds=settings.llm_timeout_seconds,
            readiness_path=settings.llm_readiness_path,
            max_output_tokens=settings.llm_max_output_tokens,
        ))
    if settings.llm_base_url and settings.llm_model:
        registry.register(OpenAICompatibleProvider(
            provider_id="custom",
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model_name=settings.llm_model,
            timeout_seconds=settings.llm_timeout_seconds,
            readiness_path=settings.llm_readiness_path,
            max_output_tokens=settings.llm_max_output_tokens,
        ))
    if settings.llm_default_model:
        registry.configure_default(settings.llm_default_model)
    else:
        first_available = next(
            (item.id for item in registry.list_models() if item.available),
            None,
        )
        if first_available is not None:
            registry.configure_default(first_available)
    return registry


llm_registry = build_llm_registry()
llm_provider = RoutingLLMProvider(llm_registry)
