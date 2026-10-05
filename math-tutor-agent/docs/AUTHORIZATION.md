# 身份认证与数据归属设计

## 1. 认证方式

API 使用 OAuth2 Password Flow 的 Bearer Access Token：

- 密码使用 Argon2 单向哈希，数据库不保存明文密码；
- JWT 使用固定算法列表校验，不读取令牌中的算法决定验证方式；
- 令牌包含 `sub`、`role`、`ver`、`iss`、`aud`、`iat`、`exp` 和 `jti`；
- Access Token 默认有效期为 30 分钟；
- Refresh Token 通过 HttpOnly Cookie 保存，默认有效期 30 天，每次刷新都会轮换；
- 服务端只保存 Refresh Token 的 SHA-256 摘要，并记录令牌家族和替换链；
- 已使用的 Refresh Token 再次出现时视为重放，服务端撤销整个家族并增加 `token_version`；
- 每次请求重新读取用户状态与 `token_version`，停用账号或退出登录后旧令牌失效；
- 非开发环境要求至少 32 字符的 `AUTH_JWT_SECRET`。
- 登录、注册和家长关联写接口使用 Redis 按 IP、账号及二者组合限流；超过阈值返回 429，Redis 不可用时生产环境返回 503。

前端把短期 Access Token 放在 `sessionStorage`，Refresh Token 对 JavaScript 不可见。Access Token 过期后，前端调用 `POST /v1/auth/refresh`，服务端消费旧 Refresh Token、签发新令牌并更新 Cookie。生产环境强制使用 HTTPS、`Secure` Cookie 和受限 `SameSite` 策略。

## 2. 邮箱验证与密码生命周期

- 新注册用户的 `email_verified_at` 为空，验证完成前不能登录；
- 邮箱验证链接默认 24 小时有效；
- 密码重置链接默认 30 分钟有效；
- 验证和重置令牌由安全随机数生成，数据库只保存 SHA-256 摘要；
- 同一用户重新申请同类链接时，旧的未使用链接立即失效；
- 忘记密码接口始终返回相同提示，不通过响应透露邮箱是否注册；
- 密码修改要求当前密码，密码重置和密码修改都会撤销全部 Refresh Session 并使旧 Access Token 失效；
- 邮件通过 SMTP Provider 发送，生产环境必须配置 SMTP；开发环境可显式开启一次性开发链接。

## 3. 角色权限

| 操作 | 学生 | 家长 | 管理员 |
| --- | --- | --- | --- |
| 注册、登录、查看本人资料 | 是 | 是 | 管理员账号不开放公开注册 |
| 创建学习会话 | 仅本人 | 否 | 否 |
| 提交辅导消息 | 仅本人会话 | 否 | 否 |
| 查看会话 | 仅本人 | 仅已授权学生 | 可查看指定学生 |
| 查看学习记录与家长报告 | 仅本人 | 仅已授权学生 | 可查看指定学生 |
| 发起家长学生关联 | 否 | 是 | 否 |
| 确认关联 | 是，且只能确认发给自己的申请 | 否 | 否 |
| 解除关联 | 关联双方 | 关联双方 | 后续管理端实现 |

学生访问其他学生 ID 时返回拒绝。按会话 ID 查询但没有权限时统一返回 404，避免通过响应差异判断会话是否存在。

## 4. 家长授权流程

1. 学生和家长分别注册账号。
2. 家长通过学生邮箱调用 `POST /v1/auth/guardian-links`，关联状态为 `pending`。
3. 学生登录后查看关联申请。
4. 学生调用 `POST /v1/auth/guardian-links/{link_id}/accept`，状态变为 `active`。
5. 家长在查询接口传入 `student_id`，服务端每次检查有效关联。
6. 任意一方解除关联后状态变为 `revoked`，家长立即失去读取权限。

不能仅凭家长知道学生邮箱就授予数据访问权。

## 5. API

| 方法与路径 | 说明 |
| --- | --- |
| `POST /v1/auth/register` | 注册学生或家长账号 |
| `POST /v1/auth/token` | 使用表单字段 `username=email` 和 `password` 登录 |
| `POST /v1/auth/refresh` | 轮换 Refresh Token 并取得新的 Access Token |
| `GET /v1/auth/me` | 获取当前身份和资料 |
| `POST /v1/auth/logout` | 撤销当前 Refresh Token 家族，并使已签发 Access Token 失效 |
| `POST /v1/auth/email-verification/request` | 重新发送邮箱验证邮件 |
| `POST /v1/auth/email-verification/confirm` | 消费一次性令牌并确认邮箱 |
| `POST /v1/auth/password/forgot` | 请求密码重置邮件，始终返回统一提示 |
| `POST /v1/auth/password/reset` | 使用一次性令牌设置新密码 |
| `POST /v1/auth/password/change` | 登录状态下验证当前密码并修改密码 |
| `POST /v1/auth/guardian-links` | 家长发起关联申请 |
| `GET /v1/auth/guardian-links` | 查看与本人相关的关联 |
| `POST /v1/auth/guardian-links/{link_id}/accept` | 学生确认关联 |
| `DELETE /v1/auth/guardian-links/{link_id}` | 任意一方解除关联 |

所有 `/v1/tutoring/**` 接口现在都要求 `Authorization: Bearer <token>`。家长和管理员调用列表、学习记录或报告接口时必须传 `student_id`。

## 6. 数据库变化

迁移 `20260928_0002` 为 `users` 增加：

- `email`：大小写归一化后的登录邮箱，唯一；
- `password_hash`：Argon2 哈希；
- `token_version`：批量撤销旧令牌；
- `last_login_at`：最近成功登录时间。

已有开发账号会迁移为 `legacy-{id}@invalid.local`，密码哈希设为不可登录标记 `!`。这些账号不会因为迁移自动获得登录能力。

迁移 `20260928_0003` 增加：

- `users.email_verified_at`：邮箱确认时间；迁移前已有账号按历史兼容策略标记为已验证；
- `account_action_tokens`：邮箱验证和密码重置的一次性令牌摘要、用途、有效期和使用时间；
- `refresh_sessions`：Refresh Token 摘要、家族、替换链、有效期和撤销状态。

## 7. 认证限流

登录、注册、关联创建、关联确认和关联解除均已接入共享 Redis 限流。Redis 键只保存邮箱、用户 ID 和 IP 的 HMAC 摘要。登录成功会清除对应账号和组合计数，但保留 IP 总量限制。阈值、故障策略和反向代理配置见 `docs/RATE_LIMITING.md`。

## 8. 后续安全工作

- 增加定时清理过期账号操作令牌和 Refresh Session 的维护任务；
- 管理员账号通过受控后台创建，并增加审计日志和更强认证；
- 对未成年人数据补充监护授权、隐私政策确认、导出和删除流程；
- 生产环境将 JWT 密钥放入密钥管理服务并定期轮换。
