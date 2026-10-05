# Redis 生产故障策略

## 1. 决策

生产环境采用**按职责分级**的 Redis 故障策略：

- 涉及安全和写入协调的能力快速失败；
- 只影响读取性能的缓存继续运行并回源 MySQL；
- MySQL 始终是正式业务数据源。

该策略由 `APP_ENV`、`REDIS_ENABLED`、`REDIS_COORDINATION_FAIL_CLOSED` 和 `AUTH_RATE_LIMIT_FAIL_CLOSED` 共同约束。非开发环境启动时强制要求：

```dotenv
REDIS_ENABLED=true
REDIS_COORDINATION_FAIL_CLOSED=true
AUTH_RATE_LIMIT_FAIL_CLOSED=true
```

配置不符合要求时应用拒绝启动，避免生产实例在无保护状态下运行。

## 2. 故障矩阵

| Redis 能力 | 生产策略 | API 行为 | 原因 |
| --- | --- | --- | --- |
| 认证接口限流 | 快速失败 | HTTP 503，`Retry-After: 2` | 继续运行会允许撞库、批量注册或关联滥用绕过限流 |
| 会话分布式锁获取 | 快速失败 | HTTP 503，`Retry-After: 2` | 避免多个 API 实例同时调用模型并更新同一会话 |
| 幂等结果读取 | 快速失败 | HTTP 503，`Retry-After: 2` | 无法确认 `client_turn_id` 是否已经执行时，不再次调用模型 |
| 幂等结果 JSON 损坏 | 快速失败 | HTTP 503，`Retry-After: 2` | 把损坏内容当作未命中可能重复执行已完成请求 |
| 会话缓存读取 | 继续运行 | 回源 MySQL | 缓存缺失只增加数据库读取，不改变业务语义 |
| 会话缓存写入/删除 | 继续运行 | 返回原业务结果并记录日志 | MySQL 已保存正式数据，缓存可在后续请求重建 |
| RAG 查询缓存读取/写入 | 继续运行 | 绕过缓存并调用原检索 Provider | Redis 只保存可重建的结构化检索结果 |
| RAG generation Redis 镜像更新 | 继续运行 | 使用 MySQL generation | MySQL 是缓存版本的事实来源，Redis 恢复后会重新同步 |
| 幂等结果写入 | 已提交后继续返回 | 返回已完成业务结果并记录高优先级日志 | MySQL 事务已经提交，此时改报 503 会诱导客户端重试已完成操作 |
| 锁释放失败 | 返回已完成结果 | 记录日志，等待锁 TTL 自动释放 | 业务事务已经结束，锁有 120 秒默认过期时间 |
| Redis 锁等待超时 | 业务冲突 | HTTP 409 | Redis 可用，但同一会话正在被另一个请求处理 |

MySQL `learning_sessions.version` 乐观锁是第二道保护。当 Redis 在非生产环境被配置为继续运行时，并发写仍不会互相覆盖；失败事务返回 HTTP 409。但乐观锁不能避免重复模型调用，所以生产环境仍要求锁和幂等读取快速失败。

## 3. 请求处理边界

辅导请求在调用 Agent 之前完成两项检查：

1. 获取 Redis 会话锁；
2. 使用 `client_turn_id` 查询 Redis 幂等结果。

任一协调操作不可用时立即结束请求，不调用模型、不写入 MySQL。客户端收到 503 后应保留原来的 `client_turn_id`，等待至少 `Retry-After` 指定的时间，再以指数退避和少量随机抖动重试。

会话缓存不参与正确性判断。缓存读取失败时直接从 MySQL 载入包含最新 `version` 的会话；缓存写入失败时，当前响应仍以已经提交的 MySQL 数据为准。

## 4. 开发环境

本地没有 Redis 时可以显式使用：

```dotenv
APP_ENV=development
REDIS_ENABLED=false
AUTH_RATE_LIMIT_ENABLED=false
```

也可以保留 Redis 客户端但允许教学协调降级：

```dotenv
APP_ENV=development
REDIS_ENABLED=true
REDIS_COORDINATION_FAIL_CLOSED=false
AUTH_RATE_LIMIT_FAIL_CLOSED=false
```

该模式依靠 MySQL 乐观锁防止覆盖，适合本地开发，不应用于生产或预发布环境。

## 5. 监控与恢复

生产监控至少区分以下指标：

- Redis 连接和命令错误率；
- 认证限流快速失败次数；
- 会话锁获取错误、等待超时和释放错误；
- 幂等读取及写入错误；
- 会话缓存命中率和回源 MySQL 次数；
- MySQL 乐观锁冲突次数；
- HTTP 503 和 409 的接口、持续时间与恢复时间。

短时故障由客户端受控重试。持续故障应停止接收新的辅导写请求，恢复 Redis 后再逐步放量。不要在故障期间临时关闭生产快速失败开关。

`GET /v1/health/ready` 会执行 Redis `PING`。探测失败时返回 503，负载均衡器可以据此停止向该实例分配新流量；存活检查不访问 Redis，因此不会因为 Redis 故障重启 API 进程。
