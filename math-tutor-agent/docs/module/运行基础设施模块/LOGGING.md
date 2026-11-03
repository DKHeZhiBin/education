# 后端日志系统

## 目标

日志用于回答四类调试问题：一次 HTTP 请求是否成功、它对应哪个辅导会话、Agent 本轮运行了哪些步骤、错误发生在哪一层。默认不记录题目全文、学生作答、模型 Prompt、完整请求头、Cookie 或凭据。

系统使用 Python 标准 `logging`，业务模块继续通过 `logging.getLogger(__name__)` 写日志，不与具体日志平台绑定。以后接入 Loki、ELK、Datadog 或云日志时，可以直接采集 JSON 文件或标准输出。

## 输出文件

默认目录为 `math-tutor-agent/.local-services/logs/`：

| 文件 | 内容 | 用途 |
| --- | --- | --- |
| `app.log` | `LOG_LEVEL` 以上的应用、请求、Agent 和依赖日志 | 日常调试和完整链路检索 |
| `error.log` | `ERROR` 及以上日志，包含异常堆栈 | 快速定位服务异常 |
| `api.log` | Uvicorn 启动器的标准输出和进程错误 | 排查 API 无法启动或进程退出 |

`app.log` 与 `error.log` 默认使用单行 JSON。文件达到 10 MiB 后轮转，分别保留 5 份历史文件。最坏情况下两组应用日志约占 120 MiB。

## 请求关联

每次 HTTP 请求都会获得 `request_id`：

1. 前端传入合法的 `X-Request-ID` 时沿用该值。
2. 没有传入时由 API 生成 UUID。
3. 响应头始终返回 `X-Request-ID`。
4. 请求期间由 Agent、Service、Repository 和 Provider 写出的日志自动带上相同的 `request_id`。
5. URL 包含辅导会话 ID 时，日志还会自动带上 `session_id`。

前端遇到错误时可以保存响应头中的 `X-Request-ID`，后端据此查出同一请求的完整日志链路。

## 结构化字段

每条 JSON 日志至少包含：

- `timestamp`：UTC ISO 8601 时间。
- `level`：日志级别。
- `logger`：产生记录的 Python 模块。
- `message`：简短事件描述。
- `environment`：运行环境。
- `request_id`、`session_id`：请求和会话关联标识。
- `process_id`：进程 ID。

HTTP 请求会补充 `request_method`、`request_path`、`status_code` 和 `duration_ms`。Agent 完成事件会补充 `run_id`、`artifact_kinds`、会话状态及降级原因。超过 `LOG_SLOW_REQUEST_MS` 的请求按 `WARNING` 记录。

## 日志等级

| 等级 | 使用场景 |
| --- | --- |
| `DEBUG` | 本地短期诊断、缓存选择和分支判断；默认关闭 |
| `INFO` | 请求完成、Agent 运行完成、应用启停和正常状态变化 |
| `WARNING` | 可恢复的依赖失败、降级、慢请求、4xx 冲突或限流 |
| `ERROR` | 请求未处理异常、数据写入失败和不可恢复的本轮错误 |
| `CRITICAL` | 无法继续提供服务或存在数据完整性风险 |

业务代码使用稳定的 `event` 字段，避免后续依赖可变的自然语言消息：

```python
import logging

logger = logging.getLogger(__name__)

logger.info(
    "Knowledge retrieval completed",
    extra={
        "event": "rag.retrieval.completed",
        "session_id": session_id,
        "duration_ms": duration_ms,
        "log_result_count": result_count,
    },
)
```

自定义结构化字段统一使用 `log_` 前缀，写入 JSON 时前缀会被移除。禁止把完整题目、作答、Prompt、模型原始回复或用户邮箱放进 `extra`。

## 敏感信息保护

所有输出处理器写入前都会过滤以下内容：

- Bearer Token、Refresh Token 和普通 Token。
- 密码、Cookie、Authorization、Secret 与 API Key。
- MySQL、Redis 等连接 URL 中的密码。

过滤器是最后一道保护。业务代码仍须遵守数据最小化原则，只记录标识、状态、耗时、数量、版本和安全错误摘要。异常对象也可能携带上游响应，因此 Provider 不应把完整请求正文加入异常信息。

配置类中的 Provider Key 默认值保持为空，真实 Key 只放在本机 `.env` 或部署环境的密钥管理系统中。

## 配置

```dotenv
LOG_LEVEL=INFO
LOG_CONSOLE_ENABLED=true
LOG_FILE_ENABLED=true
LOG_JSON_FILE=true
LOG_DIRECTORY=.local-services/logs
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
LOG_SLOW_REQUEST_MS=1500
LOG_HEALTH_REQUESTS=false
```

- 本地开发推荐同时开启控制台和文件日志。
- 健康检查默认不记录，避免轮询淹没业务日志。
- 临时深度调试可以改为 `LOG_LEVEL=DEBUG`，问题解决后恢复 `INFO`。
- 容器或多进程生产部署建议设置 `LOG_FILE_ENABLED=false`，由标准输出采集器统一轮转；多个进程不应同时轮转同一个本地文件。

## 常用调试方式

查看日志位置：

```bash
./math-tutor-agent/scripts/dev-stack logs
```

持续查看应用日志：

```bash
tail -f math-tutor-agent/.local-services/logs/app.log
```

按一次请求查询：

```bash
jq 'select(.request_id == "替换为响应头中的请求ID")' \
  math-tutor-agent/.local-services/logs/app.log
```

查看 Agent 运行和慢请求：

```bash
jq 'select(.event == "agent.run.completed" or .slow == true)' \
  math-tutor-agent/.local-services/logs/app.log
```

查看错误：

```bash
tail -n 100 math-tutor-agent/.local-services/logs/error.log
```

轮转后的文件名为 `app.log.1`、`app.log.2` 和 `error.log.1` 等。排查跨轮转时间段时应同时搜索这些文件。

## 后续扩展

当前版本已经覆盖应用、HTTP 和 Agent 完成事件。后续可在同一字段规范上增加：

- LLM Provider 的模型、输入输出 token 数、耗时和费用摘要。
- Redis 缓存命中、锁等待和幂等命中指标。
- MySQL 慢查询、连接池和乐观锁冲突指标。
- RAG 召回、重排和降级指标。

这些数据只记录统计值和版本标识，不记录学生内容正文。

## 相关代码

- [结构化日志配置](../../../app/core/logging.py)
- [应用启动日志接入](../../../app/main.py)
- [日志运行配置](../../../app/core/config.py)
