import json
import re
from typing import Any

import httpx

from app.core.config import settings


class OpenAICompatibleProvider:
    """Small provider adapter shared by the specialist agents."""

    @property
    def model_name(self) -> str:
        return settings.llm_model

    @property
    def available(self) -> bool:
        return bool(settings.llm_base_url and settings.llm_model)

    def complete_json(self, system: str, user: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        try:
            response = httpx.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json={
                    "model": settings.llm_model,
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_json(content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def check_readiness(self) -> tuple[bool, str]:
        if not self.available:
            return False, "not_configured"
        if not settings.llm_readiness_path:
            return True, "configuration_only"
        headers: dict[str, str] = {}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        try:
            response = httpx.get(
                f"{settings.llm_base_url.rstrip('/')}{settings.llm_readiness_path}",
                headers=headers,
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

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        candidate = fenced.group(1) if fenced else content.strip()
        parsed = json.loads(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Agent output must be a JSON object")
        return parsed


llm_provider = OpenAICompatibleProvider()
