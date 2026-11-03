from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


AudioOutputFormat = Literal["mp3", "wav", "opus"]


class SpeechProviderError(RuntimeError):
    """中文：表示语音供应商调用失败，并携带稳定且可重试的错误语义。
    English: Represents a speech provider failure with stable retry semantics.
    """

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        """中文：用安全错误码和可重试标志初始化异常。
        English: Initializes the error with a safe code and retryable flag.
        """
        super().__init__(code)
        self.code = code
        self.retryable = retryable


class ASRProviderError(SpeechProviderError):
    """中文：表示语音转文字 Provider 的受控失败。
    English: Represents a controlled automatic speech recognition provider failure.
    """


class TTSProviderError(SpeechProviderError):
    """中文：表示文字转语音 Provider 的受控失败。
    English: Represents a controlled text-to-speech provider failure.
    """


@dataclass(frozen=True)
class ASRCapabilities:
    """中文：声明 ASR 适配器支持的格式、语言及输入限制。
    English: Declares formats, languages, and input limits supported by an ASR adapter.
    """

    supported_mime_types: tuple[str, ...]
    supported_languages: tuple[str, ...] = ()
    max_audio_bytes: int | None = None
    supports_word_timestamps: bool = False
    supports_context_phrases: bool = False


@dataclass(frozen=True)
class ASRRequest:
    """中文：描述一次受控语音转写请求，不包含存储路径或用户凭证。
    English: Describes a controlled transcription request without storage paths or credentials.
    """

    content: bytes
    mime_type: str
    filename: str
    language_hint: str | None = None
    context_phrases: tuple[str, ...] = ()
    enable_punctuation: bool = True
    enable_word_timestamps: bool = False


@dataclass(frozen=True)
class TranscriptSegment:
    """中文：表示带时间范围和置信度的一段转写文本。
    English: Represents a transcript segment with timing and confidence.
    """

    text: str
    start_ms: int
    end_ms: int
    confidence: float | None = None
    speaker: str | None = None


@dataclass(frozen=True)
class ASRResult:
    """中文：保存完整转写、分段、语言、时长和供应商来源。
    English: Stores the full transcript, segments, language, duration, and provider provenance.
    """

    transcript: str
    language: str | None
    duration_ms: int | None
    confidence: float | None
    segments: tuple[TranscriptSegment, ...]
    provider_id: str
    model_name: str


class ASRProvider(Protocol):
    """中文：定义可替换的自动语音识别 Provider 接口。
    English: Defines a replaceable automatic speech recognition provider interface.
    """

    @property
    def provider_id(self) -> str:
        """中文：返回稳定的供应商标识。
        English: Returns the stable provider identifier.
        """
        ...

    @property
    def model_name(self) -> str:
        """中文：返回实际执行转写的模型名称。
        English: Returns the model used for transcription.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：返回 ASR Provider 是否已具备运行条件。
        English: Returns whether the ASR provider is ready for use.
        """
        ...

    @property
    def capabilities(self) -> ASRCapabilities:
        """中文：返回调用前可检查的 ASR 能力和限制。
        English: Returns ASR capabilities and limits that callers can check in advance.
        """
        ...

    def transcribe(self, request: ASRRequest) -> ASRResult:
        """中文：将音频转换为带来源信息的结构化文本。
        English: Converts audio into structured text with provenance.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：检查 ASR 服务是否可访问。
        English: Checks whether the ASR service is reachable.
        """
        ...


@dataclass(frozen=True)
class TTSCapabilities:
    """中文：声明 TTS 适配器支持的语言、音频格式、音色和文本限制。
    English: Declares languages, audio formats, voices, and text limits supported by TTS.
    """

    supported_formats: tuple[AudioOutputFormat, ...]
    supported_languages: tuple[str, ...] = ()
    voice_ids: tuple[str, ...] = ()
    max_input_characters: int | None = None
    supports_speaking_rate: bool = False
    supports_pitch: bool = False
    supports_style: bool = False


@dataclass(frozen=True)
class TTSRequest:
    """中文：描述文字转语音请求及受限的朗读参数。
    English: Describes a text-to-speech request and constrained speaking parameters.
    """

    text: str
    language: str
    voice_id: str | None = None
    output_format: AudioOutputFormat = "mp3"
    speaking_rate: float = 1.0
    pitch: float = 0.0
    style: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class TTSResult:
    """中文：保存生成音频、媒体信息、时长和供应商来源。
    English: Stores generated audio, media metadata, duration, and provider provenance.
    """

    content: bytes
    mime_type: str
    duration_ms: int | None
    sample_rate_hz: int | None
    provider_id: str
    model_name: str
    voice_id: str | None


class TTSProvider(Protocol):
    """中文：定义可替换的文字转语音 Provider 接口。
    English: Defines a replaceable text-to-speech provider interface.
    """

    @property
    def provider_id(self) -> str:
        """中文：返回稳定的供应商标识。
        English: Returns the stable provider identifier.
        """
        ...

    @property
    def model_name(self) -> str:
        """中文：返回实际执行合成的模型名称。
        English: Returns the model used for synthesis.
        """
        ...

    @property
    def available(self) -> bool:
        """中文：返回 TTS Provider 是否已具备运行条件。
        English: Returns whether the TTS provider is ready for use.
        """
        ...

    @property
    def capabilities(self) -> TTSCapabilities:
        """中文：返回调用前可检查的 TTS 能力和限制。
        English: Returns TTS capabilities and limits that callers can check in advance.
        """
        ...

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """中文：将文本转换为带来源信息的音频。
        English: Converts text into audio with provenance.
        """
        ...

    def check_readiness(self) -> tuple[bool, str]:
        """中文：检查 TTS 服务是否可访问。
        English: Checks whether the TTS service is reachable.
        """
        ...


@dataclass(frozen=True)
class DisabledASRProvider:
    """中文：在未接入语音识别服务时提供安全降级实现。
    English: Provides a safe fallback when no speech recognition service is connected.
    """

    provider_id: str = "disabled"
    model_name: str = "disabled"
    available: bool = False
    capabilities: ASRCapabilities = field(default_factory=lambda: ASRCapabilities(()))

    def transcribe(self, request: ASRRequest) -> ASRResult:
        """中文：拒绝未配置的转写请求并返回稳定错误码。
        English: Rejects transcription when ASR is not configured with a stable code.
        """
        raise ASRProviderError("asr_not_configured")

    def check_readiness(self) -> tuple[bool, str]:
        """中文：报告 ASR 尚未配置。
        English: Reports that ASR is not configured.
        """
        return False, "not_configured"


@dataclass(frozen=True)
class DisabledTTSProvider:
    """中文：在未接入语音合成服务时提供安全降级实现。
    English: Provides a safe fallback when no speech synthesis service is connected.
    """

    provider_id: str = "disabled"
    model_name: str = "disabled"
    available: bool = False
    capabilities: TTSCapabilities = field(default_factory=lambda: TTSCapabilities(()))

    def synthesize(self, request: TTSRequest) -> TTSResult:
        """中文：拒绝未配置的合成请求并返回稳定错误码。
        English: Rejects synthesis when TTS is not configured with a stable code.
        """
        raise TTSProviderError("tts_not_configured")

    def check_readiness(self) -> tuple[bool, str]:
        """中文：报告 TTS 尚未配置。
        English: Reports that TTS is not configured.
        """
        return False, "not_configured"


asr_provider: ASRProvider = DisabledASRProvider()
tts_provider: TTSProvider = DisabledTTSProvider()
