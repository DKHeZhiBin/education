# 辅导 API 错误响应

## 1. 响应契约

`/v1/tutoring/*` 的非成功响应统一返回顶层 JSON：

```json
{
  "code": "session_busy",
  "message": "上一条消息仍在处理中，正在为你同步最新会话。",
  "retryable": true,
  "retry_after_seconds": 1
}
```

前端只能使用 `code`、`retryable`、HTTP 状态和可选的 `retry_after_seconds` 决定行为。`message` 只用于展示，不作为状态判断条件。

请求字段校验失败时还会返回 `fields`，其中只保存字段路径与错误类型，不把内部异常或请求正文返回给客户端。

## 2. 主要错误码

| HTTP | `code` | `retryable` | 前端行为 |
| ---: | --- | --- | --- |
| 401 | `authentication_required` | false | 清除失效访问令牌并进入登录流程 |
| 403 | `tutoring_access_denied` | false | 展示无权访问，不重试 |
| 404 | `session_not_found` | false | 返回学习入口 |
| 404 | `problem_unavailable` | false | 提示题目不可用于学习 |
| 409 | `session_busy` | true | 等待指定时间、同步会话、复用原 `client_turn_id` |
| 409 | `session_version_conflict` | true | 同步最新版本、复用原 `client_turn_id` |
| 422 | `invalid_tutoring_request` | false | 标记输入问题 |
| 422 | `llm_model_unavailable` | false | 要求重新选择可用模型 |
| 503 | `agent_budget_exceeded` | true | 保留输入并稍后重试 |
| 503 | `session_coordination_unavailable` | true | 保留输入和幂等键，按建议时间重试 |

未显式登记的 HTTP 异常由辅导 API 边界按状态码映射到稳定兜底错误码。非辅导接口继续使用各自的响应契约。

## 3. 实现边界

- `app.services.tutoring` 为已知业务失败指定精确错误码；
- 辅导 API 异常处理器将身份依赖和其他 HTTP 异常规范化；
- 请求校验异常统一为 `invalid_tutoring_request`；
- OpenAPI 为辅导路由登记 `TutoringAPIErrorResponse`；
- 前端 `TutoringHttpError` 保存状态、错误码、是否可重试和等待时间。

## 4. SSE 错误

`POST /v1/tutoring/sessions/{session_id}/turns/stream` 在建立流之前仍使用上述 HTTP 错误响应。流建立后的业务失败使用 `turn.error` 事件，事件数据保留相同的 `code + message + retryable + retry_after_seconds` 字段。前端将两种来源统一转换为 `TutoringHttpError`，并在可重试错误中保留原消息与 `client_turn_id`。

## 相关代码

- [统一 API 错误对象](../../../app/api/errors.py)
- [辅导接口错误映射](../../../app/api/routes/tutoring.py)
- [学生端 API 错误处理](../../../../src/services/tutoring.ts)
- [学习工作区冲突与重试交互](../../../../src/features/learning/LearningWorkspace.tsx)
