# ASR / TTS Provider 设计

最后更新：2026-10-16

## 目标

语音能力作为文字辅导之外的可选输入输出适配器。业务层只依赖 `ASRProvider` 和 `TTSProvider`，不依赖腾讯云、Google、OpenAI 或本地模型的专有 DTO。未配置语音服务时，文字输入、图片 OCR 和文字回复继续运行。

接口位于 `app/providers/speech.py`。

## ASR：语音转文字

### 输入 `ASRRequest`

| 字段 | 含义 |
| --- | --- |
| `content` | 已通过大小和格式校验的音频字节 |
| `mime_type` | 服务端确认的真实媒体类型 |
| `filename` | 仅用于展示或向供应商提供格式提示 |
| `language_hint` | 可选语言提示，例如 `zh-CN` |
| `context_phrases` | 本轮数学术语、符号读法和知识点提示 |
| `enable_punctuation` | 是否请求自动标点 |
| `enable_word_timestamps` | 是否请求词级时间戳 |

`context_phrases` 只能放入当前题目需要的有限数学词汇，不能塞入学生历史、账号信息或标准答案。

### 输出 `ASRResult`

- 完整转写文本；
- 识别语言、音频时长和整体置信度；
- 可选的 `TranscriptSegment` 分段、起止毫秒、分段置信度和说话人；
- 实际 Provider 与模型名称，便于审计和回放问题。

ASR 结果属于候选输入。低置信度、数学符号读法冲突或文本不完整时，前端必须让学生确认，不能直接作为有效作答证据。

## TTS：文字转语音

### 输入 `TTSRequest`

| 字段 | 含义 |
| --- | --- |
| `text` | 已通过长度限制的辅导回复文本 |
| `language` | 朗读语言 |
| `voice_id` | Provider 公开的音色标识 |
| `output_format` | `mp3`、`wav` 或 `opus` |
| `speaking_rate` | 语速，业务层提交前应按 Provider 能力限制 |
| `pitch` | 音高，Provider 不支持时必须拒绝或显式忽略 |
| `style` | 可选朗读风格，不允许注入供应商脚本 |
| `idempotency_key` | 重试时复用，避免重复生成与重复计费 |

### 输出 `TTSResult`

- 音频字节和真实 MIME；
- 可选时长及采样率；
- Provider、模型和实际音色来源。

首版接口只接受纯文本，不接受任意 SSML，避免外部标签、音频引用和供应商指令穿透。公式朗读应在业务层先转换成适合学生理解的口语文本，再交给 TTS。

## 能力声明

调用方必须先读取 `ASRCapabilities` 或 `TTSCapabilities`，检查：

- 支持的音频 MIME、输出格式和语言；
- 最大音频字节数或最大文本字符数；
- 是否支持上下文词、时间戳、语速、音高和风格；
- 可选音色列表。

业务层不能根据供应商名称猜测能力。

## 错误与降级

Provider 抛出 `ASRProviderError` 或 `TTSProviderError`，包含稳定 `code` 和 `retryable`，供应商原始错误和凭证不得透传给前端。

未配置时使用 `DisabledASRProvider` 和 `DisabledTTSProvider`：

- `transcribe` 返回 `asr_not_configured`；
- `synthesize` 返回 `tts_not_configured`；
- `/health/ready` 中分别显示 `asr`、`tts` 为 `disabled`；
- 默认不影响整体 readiness。

只有部署明确将 `ASR_REQUIRED_FOR_READINESS` 或 `TTS_REQUIRED_FOR_READINESS` 设为 `true` 时，对应服务不可用才阻断上线。

## 配置边界

```dotenv
ASR_AUDIO_MAX_BYTES=26214400
ASR_TIMEOUT_SECONDS=60
ASR_REQUIRED_FOR_READINESS=false
TTS_MAX_INPUT_CHARACTERS=5000
TTS_TIMEOUT_SECONDS=30
TTS_REQUIRED_FOR_READINESS=false
```

这些配置定义业务层上限。具体供应商适配器仍需使用自身更严格的限制。

## 后续接入顺序

1. 选择首个 ASR 和 TTS 供应商，分别实现 Protocol。
2. 增加音频文件头检测、时长检查和受控存储。
3. 建立上传、转写、学生确认、语音合成和下载鉴权 API。
4. 将 `media_assets.media_type` 分别写为 `audio` 和 `tts`，保存模型来源与处理状态。
5. 增加超时、幂等、清理、费用上限和低置信度人工确认规则。

Provider 接口本身不等于允许语音数据流入 Agent。只有学生确认后的 ASR 文本可以进入本轮辅导上下文。

## 相关代码

- [ASR/TTS Provider](../../../app/providers/speech.py)
- [媒体附件模型](../../../app/models/media.py)
- [运行配置](../../../app/core/config.py)
