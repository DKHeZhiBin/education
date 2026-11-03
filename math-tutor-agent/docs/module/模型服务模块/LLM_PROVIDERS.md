# 多 LLM Provider 与用户模型选择

## 1. 设计目标

用户可以在创建学习会话时选择服务端允许的模型。首批支持 DeepSeek 和 Gemini；Agent、Harness 和业务服务只依赖 `LLMProvider` 协议，不依赖具体厂商 SDK。

客户端不能提交 API Key、Base URL 或任意模型地址。密钥由服务端环境变量管理，模型列表来自 `LLMProviderRegistry` 白名单。

## 2. 组件

| 组件 | 职责 |
| --- | --- |
| `LLMProvider` | 统一的 JSON 调用、可用性与就绪检查协议 |
| `OpenAICompatibleProvider` | 调用 OpenAI Chat Completions 格式的通用适配器 |
| `LLMProviderRegistry` | 注册模型、默认模型、白名单查询和按 Provider/模型解析 |
| `RoutingLLMProvider` | 使用 `ContextVar` 保存当前请求模型，保证并发会话互不串模型 |
| `GET /v1/llm/models` | 返回前端可选择的模型及配置状态 |
| `learning_sessions.llm_model_id` | 固定会话模型，格式为 `provider/model` |

DeepSeek 和 Gemini 都使用各自官方的 OpenAI 兼容入口。DeepSeek 官方地址为 `https://api.deepseek.com`；Gemini OpenAI 兼容地址为 `https://generativelanguage.googleapis.com/v1beta/openai`。

## 3. 配置

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODELS=deepseek-flash,deepseek-v4-pro

GEMINI_API_KEY=
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
GEMINI_MODELS=gemini-3.8-flash,gemini-3.5-flash-lite

# 可选；未设置时选择第一个已配置密钥的模型
LLM_DEFAULT_MODEL=deepseek/deepseek-flash
LLM_MAX_OUTPUT_TOKENS=8192
```

模型名称可能随供应商更新。实际联调前，应以账号控制台和官方模型列表为准修改 `DEEPSEEK_MODELS` 或 `GEMINI_MODELS`，无需改业务代码。

旧的 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL` 仍可注册为 `custom/<model>`，用于其他 OpenAI-compatible 服务。

## 4. 用户选择流程

1. 前端读取 `GET /v1/llm/models`。
2. 只允许选择 `available=true` 的模型。
3. 创建会话时提交 `llm_model_id`。
4. Harness 从注册表校验该模型，并将其写入学习会话。
5. 会话的每个后续轮次从持久化会话恢复模型选择。
6. 如果模型配置在会话期间被移除，系统进入安全降级并在响应中说明，不会静默切换到其他模型。

## 5. 题库任务与模型版本

题目生成、独立解题、AI 复核和定期重验继续使用数据库中的 `ModelVersion`。运行时根据 `ModelVersion.provider + model_name` 从同一个注册表解析实际 Provider，因此审计记录与真实调用保持一致。

将当前已配置且带密钥的模型登记到 MySQL：

```bash
math-tutor-llm sync-model-versions
```

命令只保存 Provider、模型名、API 协议、能力与非敏感配置指纹，不保存 API Key。

## 6. 联调命令

```bash
math-tutor-llm list
math-tutor-llm check deepseek/deepseek-flash
math-tutor-llm probe deepseek/deepseek-flash
math-tutor-llm check gemini/gemini-3.8-flash
math-tutor-llm probe gemini/gemini-3.8-flash
```

`check` 只检查供应商接口是否可达；`probe` 会产生一次真实模型调用，并要求返回最小 JSON 对象。

## 7. 增加新供应商

如果新供应商兼容 OpenAI Chat Completions，只需增加配置并在 `build_llm_registry()` 注册 `OpenAICompatibleProvider`。如果协议不同，则实现 `LLMProvider`，再注册到同一个 Registry。Agent、Harness、会话模型和前端目录不需要修改。

官方接口参考：

- DeepSeek：https://api-docs.deepseek.com/guides/json_mode/
- Gemini：https://ai.google.dev/gemini-api/docs/openai

## 相关代码

- [LLM 领域合约](../../../app/domain/llm.py)
- [LLM Provider 与注册表](../../../app/providers/llm.py)
- [可用模型服务](../../../app/services/llm_models.py)
- [模型列表 API](../../../app/api/routes/llm_models.py)
- [模型运行配置](../../../app/core/config.py)
- [学生端模型选择](../../../../src/features/learning/StartLearningPage.tsx)
