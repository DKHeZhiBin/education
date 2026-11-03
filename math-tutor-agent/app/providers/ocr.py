from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, settings


OCR_SYSTEM_PROMPT = """你是数学题图片转写器。只转写图片中实际出现的内容，不求解、不补条件、不猜测被遮挡的字符。
保留题号、正文、选项、图形标签和单位。数学表达式使用 LaTeX；行内公式用 $...$，独立公式用 $$...$$。
返回严格 JSON：
{
  "question_text": "完整可编辑题目",
  "formulas_latex": ["不带美元符号的 LaTeX 公式"],
  "confidence": 0.0
}
无法可靠识别时，question_text 仍保留能确认的部分，并降低 confidence。"""


class OCRProviderError(RuntimeError):
    """中文：表示 OCR 服务调用失败或返回了无效结果。
    English: Indicates that an OCR call failed or returned an invalid result.
    """

    def __init__(self, code: str) -> None:
        """中文：用稳定错误码初始化异常，避免向客户端泄露供应商响应。
        English: Initializes the error with a stable code without exposing provider responses.
        """
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class OCRRequest:
    """中文：描述发送给 OCR Provider 的受控图片输入。
    English: Describes the controlled image input sent to an OCR provider.
    """

    content: bytes
    mime_type: str
    filename: str


@dataclass(frozen=True)
class OCRResult:
    """中文：保存可编辑题目、结构化公式和识别可信度。
    English: Stores editable problem text, structured formulas, and recognition confidence.
    """

    question_text: str
    formulas_latex: tuple[str, ...]
    confidence: float
    provider_id: str
    model_name: str


class OCRProvider(Protocol):
    """中文：定义可替换的图片题目与数学公式识别接口。
    English: Defines a replaceable interface for problem image and math formula recognition.
    """

    @property
    def provider_id(self) -> str:
        """中文：返回稳定的供应商标识。
        English: Returns the stable provider identifier.
        """
        ...

    @property
    def model_name(self) -> str:
        """中文：返回实际执行识别的模型名称。
        English: Returns the model used for recognition.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：返回 Provider 是否已具备运行配置。
        English: Returns whether the provider is configured for use.
        """
        ...

    def recognize(self, request: OCRRequest) -> OCRResult:
        """中文：识别图片中的题目正文和数学公式。
        English: Recognizes problem text and mathematical formulas from an image.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：检查 OCR Provider 是否可访问。
        English: Checks whether the OCR provider is reachable.
        """
        ...


class DisabledOCRProvider:
    """中文：在未配置 OCR 时提供明确且安全的降级实现。
    English: Provides an explicit safe fallback when OCR is not configured.
    """

    provider_id = "disabled"
    model_name = "disabled"
    available = False

    def recognize(self, request: OCRRequest) -> OCRResult:
        """中文：拒绝未配置的识别请求并返回稳定错误码。
        English: Rejects recognition when OCR is not configured with a stable code.
        """
        raise OCRProviderError("ocr_not_configured")

    def check_readiness(self) -> tuple[bool, str]:
        """中文：报告 OCR 尚未配置。
        English: Reports that OCR is not configured.
        """
        return False, "not_configured"


class OpenAICompatibleOCRProvider:
    """中文：通过 OpenAI 兼容的视觉对话接口识别题目和 LaTeX 公式。
    English: Recognizes problems and LaTeX formulas through an OpenAI-compatible vision API.
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
        max_output_tokens: int = 4096,
    ) -> None:
        """中文：初始化视觉模型地址、凭证和请求限制。
        English: Initializes the vision endpoint, credentials, and request limits.
        """
        self._provider_id = provider_id
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.readiness_path = readiness_path
        self.max_output_tokens = max_output_tokens

    @property
    def provider_id(self) -> str:
        """中文：返回配置的供应商标识。
        English: Returns the configured provider identifier.
        """
        return self._provider_id

    @property
    def model_name(self) -> str:
        """中文：返回配置的视觉模型名称。
        English: Returns the configured vision model name.
        """
        return self._model_name

    @property
    def available(self) -> bool:
        """中文：仅在地址、密钥和模型均存在时启用识别。
        English: Enables recognition only when endpoint, key, and model are configured.
        """
        return bool(self.base_url and self.api_key and self.model_name)

    def recognize(self, request: OCRRequest) -> OCRResult:
        """中文：发送图片并校验模型返回的结构化识别结果。
        English: Sends the image and validates the model's structured recognition result.
        """
        if not self.available:
            raise OCRProviderError("ocr_not_configured")
        encoded = base64.b64encode(request.content).decode("ascii")
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": OCR_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请转写这张数学题图片。"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{request.mime_type};base64,{encoded}",
                            },
                        },
                    ],
                },
            ],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            parsed = self._parse_json(content)
            question_text = str(parsed.get("question_text") or "").strip()
            if not question_text:
                raise OCRProviderError("ocr_empty_result")
            formulas = tuple(
                formula.strip()
                for formula in parsed.get("formulas_latex", [])
                if isinstance(formula, str) and formula.strip()
            )
            try:
                confidence = max(0.0, min(float(parsed.get("confidence", 0.0)), 1.0))
            except (TypeError, ValueError):
                confidence = 0.0
            return OCRResult(
                question_text=question_text,
                formulas_latex=formulas,
                confidence=confidence,
                provider_id=self.provider_id,
                model_name=self.model_name,
            )
        except OCRProviderError:
            raise
        except httpx.TimeoutException as error:
            raise OCRProviderError("ocr_timeout") from error
        except httpx.HTTPStatusError as error:
            raise OCRProviderError(f"ocr_http_{error.response.status_code}") from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise OCRProviderError("ocr_invalid_response") from error

    def check_readiness(self) -> tuple[bool, str]:
        """中文：使用模型列表接口检查视觉服务连通性。
        English: Checks vision service connectivity through the model listing endpoint.
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
        """中文：构造不记录凭证的认证请求头。
        English: Builds authentication headers without logging credentials.
        """
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    @staticmethod
    def _parse_json(content: str) -> dict:
        """中文：解析纯 JSON 或 Markdown 代码块中的 JSON。
        English: Parses JSON returned directly or inside a Markdown code fence.
        """
        fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", str(content), re.DOTALL)
        parsed = json.loads(fenced.group(1) if fenced else str(content).strip())
        if not isinstance(parsed, dict):
            raise ValueError("OCR output must be a JSON object")
        return parsed


def build_ocr_provider(config: Settings = settings) -> OCRProvider:
    """中文：根据配置创建 OCR Provider，支持 Gemini 或其他兼容视觉服务。
    English: Builds an OCR provider for Gemini or another compatible vision service.
    """
    provider_name = config.ocr_provider.strip().lower()
    if not provider_name:
        return DisabledOCRProvider()
    if provider_name == "gemini":
        base_url = config.ocr_base_url or config.gemini_base_url
        api_key = config.ocr_api_key or config.gemini_api_key
        model_name = config.ocr_model
    elif provider_name in {"openai-compatible", "custom"}:
        base_url = config.ocr_base_url
        api_key = config.ocr_api_key
        model_name = config.ocr_model
    else:
        return DisabledOCRProvider()
    return OpenAICompatibleOCRProvider(
        provider_id=provider_name,
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        timeout_seconds=config.ocr_timeout_seconds,
        readiness_path=config.ocr_readiness_path,
        max_output_tokens=config.ocr_max_output_tokens,
    )


ocr_provider = build_ocr_provider()
