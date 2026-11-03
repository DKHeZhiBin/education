# 辅导 SSE 流式回复

## 1. 目标与兼容边界

流式能力使用新增端点：

```text
POST /v1/tutoring/sessions/{session_id}/turns/stream
Accept: text/event-stream
```

请求体继续使用 `TurnRequest`。原有 `POST /v1/tutoring/sessions/{session_id}/turns`、`TurnRequest` 和 `TurnResponse` 均保持不变，因此现有客户端可以继续使用 REST 调用。

SSE 的 `turn.completed` 事件在 `result` 字段中返回完整、原样的 `TurnResponse`。前端只需要把流式过程视为展示层增强，最终会话、教学回复、降级状态和来源引用仍以稳定 DTO 为准。

## 2. 事件协议

每个数据事件都携带本轮 `client_turn_id`。事件类型同时出现在 SSE `event:` 行和 JSON `type` 字段中，便于标准 SSE 客户端与基于 Fetch 的解析器使用同一协议。服务端还会发送 SSE `id`，并用注释帧保持长连接活跃。

| 事件 | 用途 | 主要数据 |
| --- | --- | --- |
| `turn.started` | 请求已接受 | `client_turn_id`、`session_id`、阶段说明 |
| `turn.progress` | Harness 正在处理 | `stage`、`message` |
| `reply.started` | 回复即将开始展示 | `action`、`hint_level` |
| `reply.delta` | 追加回复文本 | `sequence`、`delta` |
| `session.completed` | 解题会话已经结束，即将进入复盘 | `session_id`、`status=completed`、`next_route` |
| `turn.completed` | 本轮成功结束 | `result: TurnResponse` |
| `turn.error` | 建流后的业务错误 | `status`、`code`、`message`、`retryable`、可选等待时间 |

示例：

```text
event: reply.delta
id: 4
data: {"client_turn_id":"turn-123","sequence":1,"delta":"先观察等式两边的结构。","type":"reply.delta"}

event: turn.completed
id: 5
data: {"client_turn_id":"turn-123","result":{"session":{},"reply":{},"degraded":false,"degradation_code":null,"degradation_reason":null},"type":"turn.completed"}
```

## 3. 执行与重试

流式端点与 REST 端点调用同一个 `TutoringService.add_turn`，因此继续使用既有的会话锁、乐观锁和 `client_turn_id` 幂等结果。网络中断时，前端保留学生输入和原 `client_turn_id`；学生点击重试后不会重复执行已提交成功的同一轮。

身份、角色和会话归属在响应开始前校验，此类失败返回正常 HTTP 状态。响应开始后的 409、限流、模型故障和其他运行失败通过 `turn.error` 返回，错误字段与 REST 错误契约一致。

## 4. 前端行为

辅导页按以下顺序更新界面：

1. `turn.started` 和 `turn.progress` 展示当前处理阶段。
2. `reply.delta` 逐段追加到临时回复气泡。
3. 解题完成时，`session.completed` 明确通知页面进入思路复盘；同时会话中写入 `solution_completed` 审计事件。
4. `turn.completed` 用完整 `TurnResponse` 更新会话，并清除临时气泡。
5. 连接中断或可重试错误保留待发送消息和 `client_turn_id`，显示同请求重试入口。
6. HTTP 409 继续短暂等待并重新读取最新会话。

## 5. 解题结束语义

完成状态不再只依赖前端按钮。以下两种方式都可以结束“一起思考”：

1. 前端发送 `intent=complete`；
2. 已有有效解题进度且标准解法通过验证时，学生自然表达“我已经懂了”“我明白了”“做出来了”等完成确认。

服务端完成后会同时执行四个动作：将会话状态改为 `completed`、生成结构化学习记录、保存 `session_event(event=solution_completed)`、通过 SSE 发送 `session.completed`。自然语言只是触发条件，持久化状态和结构化事件才是可靠的结束标志。

## 6. 当前实现范围

首版在 Harness 执行期间发送阶段事件和保活帧；教学 Agent 完成后，把回复按自然语句拆成 `reply.delta`。事件协议已经允许未来由支持流式输出的 LLM Provider 直接写入增量文本，而无需修改 REST DTO 或页面最终状态更新逻辑。

## 相关代码

- [辅导 HTTP 与 SSE 路由](../../../app/api/routes/tutoring.py)
- [SSE 事件编码](../../../app/api/sse.py)
- [辅导应用服务](../../../app/services/tutoring.py)
- [学生端辅导 API 客户端](../../../../src/services/tutoring.ts)
- [学生端辅导页面](../../../../src/features/learning/CoachPage.tsx)
