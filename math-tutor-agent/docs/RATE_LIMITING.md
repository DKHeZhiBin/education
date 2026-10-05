# 认证接口限流设计

## 1. 目标与范围

登录、注册和家长关联属于安全敏感入口。服务使用 Redis 保存跨 API 实例共享的短期计数，同时从三个维度限制请求：

- **IP**：限制同一来源批量尝试不同账号；
- **账号**：限制攻击者更换 IP 后持续尝试同一账号；
- **IP + 账号组合**：更快阻断单一来源对单一账号的集中尝试。

限流覆盖以下写接口：

- `POST /v1/auth/register`
- `POST /v1/auth/token`
- `POST /v1/auth/refresh`
- 邮箱验证申请/确认、忘记密码、密码重置和密码修改接口
- `POST /v1/auth/guardian-links`
- `POST /v1/auth/guardian-links/{link_id}/accept`
- `DELETE /v1/auth/guardian-links/{link_id}`

登录、注册和邮件申请的账号标识是规范化邮箱；令牌消费和刷新接口使用高熵令牌作为账号维度，并在写入 Redis 键前进行 HMAC；密码修改和家长关联使用已经通过 JWT 验证的当前用户 ID。查询本人关联列表不改变数据，因此不纳入本组写操作限流。

## 2. 默认策略

| 操作 | 窗口 | IP | 账号 | IP + 账号 |
| --- | ---: | ---: | ---: | ---: |
| 登录 | 15 分钟 | 20 次 | 8 次 | 5 次 |
| 注册 | 1 小时 | 5 次 | 3 次 | 2 次 |
| 关联创建/接受/解除 | 各自独立的 1 小时窗口 | 20 次 | 10 次 | 6 次 |

每种家长关联操作使用独立键空间，创建次数不会消耗接受或解除操作的配额。登录成功后清除该邮箱的“账号”和“IP + 账号”登录计数，IP 总量计数继续保留，避免一个来源通过不断成功登录绕过 IP 保护。

超过任一限制时 API 返回 `429 Too Many Requests`，响应头 `Retry-After` 给出当前窗口剩余秒数。错误信息不透露具体触发的维度，避免向调用方泄露账号存在状态或安全策略细节。

## 3. Redis 算法与键

实现采用固定窗口计数。Lua 脚本把 `INCR`、首次 `EXPIRE` 和 TTL 读取放在一次原子操作中，避免并发请求造成计数存在但没有过期时间。

键格式：

```text
{REDIS_KEY_PREFIX}:rate-limit:auth:{action}:{scope}:{hmac_sha256}
```

示例中的 `{scope}` 为 `ip`、`account` 或 `combined`。HMAC 使用 `AUTH_JWT_SECRET`，Redis 中只保存摘要，不保存邮箱和 IP 明文。轮换 JWT 密钥会自然切换限流键空间，旧键在窗口到期后自动删除。

限流值只是整数计数，不是正式业务数据，不进入 MySQL，也不用于账号是否存在的判断。

## 4. Redis 故障策略

认证限流与教学会话缓存采用不同的故障策略：

- `AUTH_RATE_LIMIT_FAIL_CLOSED=true` 时，Redis 不可用会返回 `503 Service Unavailable`，防止攻击者通过制造或等待 Redis 故障绕过认证保护；
- 开发环境可设置 `AUTH_RATE_LIMIT_ENABLED=false`，在本地没有 Redis 时关闭限流；
- 非开发环境启用限流时，配置校验要求 `REDIS_ENABLED=true` 且 `AUTH_RATE_LIMIT_FAIL_CLOSED=true`；
- 登录成功后的计数清理属于尽力操作，清理失败不会把已经验证成功的登录改成失败。

教学会话缓存、幂等结果和锁按 `REDIS_FAILURE_POLICY.md` 的分级策略处理。认证 Redis 故障不会改变 MySQL 中的用户、关联和学习数据。

## 5. 客户端 IP 与反向代理

代码从 ASGI `Request.client.host` 读取客户端地址，不直接信任用户可以伪造的 `X-Forwarded-For` 请求头。生产环境若经过负载均衡器或反向代理，应只信任受控代理，并在 ASGI Server 的代理头配置中限定可信代理来源。配置错误会导致所有用户共用代理 IP 配额，或使伪造来源绕过 IP 维度限制。

## 6. 配置

所有阈值都能通过环境变量调整：

```dotenv
AUTH_RATE_LIMIT_ENABLED=true
AUTH_RATE_LIMIT_FAIL_CLOSED=true
AUTH_RATE_LIMIT_LOGIN_WINDOW_SECONDS=900
AUTH_RATE_LIMIT_LOGIN_IP_ATTEMPTS=20
AUTH_RATE_LIMIT_LOGIN_ACCOUNT_ATTEMPTS=8
AUTH_RATE_LIMIT_LOGIN_COMBINED_ATTEMPTS=5
AUTH_RATE_LIMIT_REGISTER_WINDOW_SECONDS=3600
AUTH_RATE_LIMIT_REGISTER_IP_ATTEMPTS=5
AUTH_RATE_LIMIT_REGISTER_ACCOUNT_ATTEMPTS=3
AUTH_RATE_LIMIT_REGISTER_COMBINED_ATTEMPTS=2
AUTH_RATE_LIMIT_GUARDIAN_WINDOW_SECONDS=3600
AUTH_RATE_LIMIT_GUARDIAN_IP_ATTEMPTS=20
AUTH_RATE_LIMIT_GUARDIAN_ACCOUNT_ATTEMPTS=10
AUTH_RATE_LIMIT_GUARDIAN_COMBINED_ATTEMPTS=6
```

上线后应根据正常登录峰值、学校或家庭共享出口 IP 的实际分布调整阈值，并监控 429 数量、维度、接口和 Redis 错误率。日志只记录操作和限流维度，不记录原始邮箱或 IP。
