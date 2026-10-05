# 生成批次管理

## 1. 目标

后台管理员可以查看生成批次，并对批次执行暂停、恢复、取消、重试和撤回已批准内容。所有写操作都在 MySQL 事务中锁定批次，成功后写入不可变管理事件。

管理接口统一使用 `/v1/admin/generation`，要求管理员身份。

## 2. 管理接口

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/batches` | 按状态分页查询批次 |
| `GET` | `/batches/{batch_id}` | 查看批次、Job、预算、用量、输出和管理事件 |
| `POST` | `/batches/{batch_id}/pause` | 将 `running` 批次暂停 |
| `POST` | `/batches/{batch_id}/resume` | 恢复 `paused` 批次 |
| `POST` | `/batches/{batch_id}/cancel` | 取消 `pending`、`running` 或 `paused` 批次 |
| `POST` | `/batches/{batch_id}/retry` | 为失败或取消的未生成位置创建新批次 |
| `POST` | `/batches/{batch_id}/withdraw-approved` | 批量撤回该批次已批准的题目 |

暂停、恢复和取消接收必填的 `reason`。重复提交已经生效的暂停、恢复或取消操作返回 `changed=false`，不重复写管理事件。

## 3. 暂停和恢复

只有 `running` 可以进入 `paused`。暂停保留已生成题目、Job 输出、累计 token、费用和执行次数。

只有 `paused` 可以恢复到 `running`。恢复前必须确认 Job 存在、仍有执行次数，并且 token、费用、时长、模型调用数和候选数预算尚未耗尽。恢复会把 `attempt_count` 增加一次。

执行器必须在每个外部模型调用和候选持久化边界重新读取批次状态，使暂停能够在一个正在进行的调用完成后生效。

## 4. 取消

取消将批次变为终态 `cancelled`，设置 `finished_at`、Job 原因和 `cancelled_by_admin` 错误码。已经生成的候选继续保留；尚未处理的位置在终态输出中标为 `skipped`。取消后不能恢复，后续只能创建重试批次。

## 5. 重试

重试只允许来源批次处于 `partial_failed`、`failed` 或 `cancelled`。新批次的 `requested_count` 等于来源批次中尚未成功生成的位置数，已成功生成的候选不会复制或再次生成。

重试复用原请求的母题、知识范围、模型、提示和预算配置，但调用方必须提供新的幂等键：

```json
{
  "reason": "供应商故障已恢复",
  "idempotency_key": "admin-retry-20261003-001"
}
```

新批次保存 `retry_of_batch_id`、`retry_of_job_id` 和原因。来源批次与重试批次各写一条互相关联的管理事件。相同幂等键的同一请求重复提交会返回已创建的重试批次。

## 6. 撤回已批准内容

撤回的目标状态是 `quarantined`，防止内容继续用于生产检索。操作在一个事务内逐题调用 `ProblemContentStateMachine`，每题写入 `ProblemStatusTransition`，并刷新批次批准数和隔离数。

对已经 `indexed` 的题目，`indexed_content_removed=true` 只表示调用方期望索引已移除，状态机仍要求数据库中存在实际通过的 `index_removal` 证据。该证据必须由 [生产索引删除与重建流程](./INDEX_LIFECYCLE.md) 在 Qdrant 删除成功后写入，不能由接口参数代替。

默认只撤回 `approved`：

```json
{
  "reason": "发现母题授权范围需要重新确认",
  "include_indexed": false,
  "indexed_content_removed": false
}
```

若同时撤回 `indexed`，必须先完成生产索引删除并写入通过的 `index_removal` 证据，然后设置 `include_indexed=true` 和 `indexed_content_removed=true`。任一题目不满足撤回条件时整个事务回滚，不产生部分撤回。默认未处理的索引题目会在 `skipped_indexed_problem_ids` 中返回。

## 7. 审计

`generation_batch_management_events` 只追加保存操作类型、操作前后状态、管理员、原因、关联重试批次、结构化载荷和操作时间。题目撤回同时保留逐题状态审计，可以从批次操作追踪到每道题的变化。
