# 本地开发服务与统一启动

项目使用隔离的 `.local-services/` 目录运行 MySQL、Redis、Qdrant 与 Qwen3 Embedding，不依赖 Docker。统一入口还会执行数据库迁移、同步知识点目录、检查 Qdrant 集合，然后依次启动 API、学生前端和知识管理端。

## 日常启动

从仓库根目录执行一条命令：

```bash
./math-tutor-agent/scripts/dev-stack start
```

固定启动顺序为：

1. 检查 `.env`、Python 虚拟环境、Node 依赖和本地服务运行时。
2. 启动 MySQL。
3. 启动 Redis。
4. 启动 Qdrant。
5. 启动 Qwen3 Embedding，并等待模型加载完成。
6. 执行 `alembic upgrade head`。
7. 幂等初始化本地开发测试账号。
8. 幂等同步版本化知识点目录、能力点和先修关系到 MySQL。
9. 创建或校验 Qdrant collection。
10. 启动 FastAPI，检查 `/v1/health/live` 与 `/v1/health/ready`。
11. 启动学生 React 前端。
12. 启动知识管理端，并用 LaunchAgent 保持运行。

成功后可以访问：

- 前端：`http://127.0.0.1:5173`
- 知识管理台：`http://127.0.0.1:5174`
- API 文档：`http://127.0.0.1:8000/docs`
- Qdrant Dashboard：`http://127.0.0.1:6333/dashboard`

## 本地测试登录账号

`dev-stack start` 会在数据库迁移后创建或恢复下面三个账号，并将邮箱标记为已验证：

| 角色 | 登录邮箱 | 密码 | 用途 |
| --- | --- | --- | --- |
| 学生 | `student.demo@example.com` | `MathTutorDemo2026!` | 创建题目、完成辅导、查看和导出学习数据 |
| 家长 | `guardian.demo@example.com` | `MathTutorDemo2026!` | 查看已授权学生的学习记录和家长报告 |
| 管理员 | `admin.demo@example.com` | `MathTutorDemo2026!` | 登录独立知识管理台，维护目录、知识点、关系和内容 |

学生和家长账号默认已经建立有效的家长授权关系。若账号被删除、密码被修改或授权被撤销，重新执行以下命令即可恢复：

```bash
cd math-tutor-agent
.venv/bin/python -m app.demo_accounts_cli
```

初始化程序只允许在 `APP_ENV=development` 下运行。以上凭据仅用于本机开发，不能用于测试、预发布或生产环境；部署前必须删除固定凭据，并通过正式注册或受控账号管理流程创建用户。

统一管理命令：

```bash
./math-tutor-agent/scripts/dev-stack check
./math-tutor-agent/scripts/dev-stack status
./math-tutor-agent/scripts/dev-stack logs
./math-tutor-agent/scripts/dev-stack stop
./math-tutor-agent/scripts/dev-stack restart
```

只恢复知识管理端而不重启其他服务时，可以执行：

```bash
./math-tutor-agent/scripts/dev-stack start-admin
```

`check` 只检查配置和运行时，不启动服务。`stop` 按管理端、学生端、API、Embedding、Qdrant、Redis、MySQL 的逆序停止本脚本管理的进程。

## 首次准备

后端配置文件：

```bash
cp math-tutor-agent/.env.example math-tutor-agent/.env
```

前端不创建 `.env` 也可以使用默认 API 地址。需要修改地址时：

```bash
cp .env.example .env
```

必须存在且非空的后端配置：

- `DATABASE_URL`
- `AUTH_JWT_SECRET`
- `REDIS_URL`
- 启用 RAG 时的 `RAG_PROVIDER`
- 使用 Qdrant 或混合检索时的 `QDRANT_URL`、`QDRANT_COLLECTION`、`QDRANT_VECTOR_NAME`
- 使用 Qdrant 或混合检索时的 `EMBEDDING_BASE_URL`、`EMBEDDING_MODEL`

DeepSeek、Gemini 和通用 LLM Key 可以不填，但此时只保证内置演示题的安全降级流程。配置至少一个 Provider Key 后才能验收开放题目。

Redis 尚未安装时，执行一次：

```bash
cd math-tutor-agent
./scripts/install-local-redis
```

Qwen3 Embedding 尚未安装时，执行一次：

```bash
cd math-tutor-agent
./scripts/install-qwen3-embedding
```

## 已安装版本

- MySQL Community Server 8.4.11 LTS
- Redis 7.4.2
- Qdrant 1.19.1
- Qwen3-Embedding-0.6B（1024 维，Apple MPS 加速）

程序、数据、配置、日志和本地密钥均位于 `.local-services/`，该目录不会进入版本控制。

服务通过当前 macOS 用户的 LaunchAgent 持续运行，并在登录后自动启动。

## 仅管理基础依赖

一般使用 `dev-stack`。只有在不需要 API 和前端时，才直接使用：

```bash
./scripts/local-services start
./scripts/local-services status
./scripts/local-services stop
./scripts/local-services restart
```

## 服务地址

- MySQL：`127.0.0.1:3306`
- Redis：`redis://127.0.0.1:6379/0`
- Qdrant REST API：`http://127.0.0.1:6333`
- Qdrant Dashboard：`http://127.0.0.1:6333/dashboard`
- Qdrant gRPC：`127.0.0.1:6334`
- Qwen3 Embedding API：`http://127.0.0.1:8100/v1`
- Qwen3 健康检查：`http://127.0.0.1:8100/health`

项目 MySQL 账号和连接地址保存在本地 `.env`。MySQL root 密钥只保存在权限为 `600` 的 `.local-services/config/mysql-root-client.cnf`。Redis 只监听本机地址，数据保存在 `.local-services/data/redis/`。

Qdrant 只监听本机回环地址，开发环境未配置 API Key。不要直接把 6333 或 6334 端口暴露到公网。

Qwen3 Embedding 同样只监听本机回环地址，提供 OpenAI 兼容的
`POST /v1/embeddings` 与 `GET /v1/models`。查询文本会自动加入数学教育检索指令，
知识文档按原文编码；两类向量均做归一化。模型运行环境、Hugging Face 缓存和日志都在
`.local-services/` 中。首次启动需要下载模型，后续直接读取本地缓存。

如需重新安装或更新独立运行环境：

```bash
./scripts/install-qwen3-embedding
./scripts/local-services restart
```

## 日志与故障定位

应用日志已经统一接入请求关联 ID、敏感信息过滤和文件轮转。完整字段、配置及查询方法见 `docs/module/运行基础设施模块/LOGGING.md`。日志位置如下：

- 应用与 Agent：`.local-services/logs/app.log`
- 应用错误：`.local-services/logs/error.log`
- API 启动器：`.local-services/logs/api.log`
- 前端：`.local-services/logs/frontend.log`
- MySQL：`.local-services/logs/mysql-error.log`
- Redis：`.local-services/logs/redis.log`
- Qdrant：`.local-services/logs/qdrant.log`
- Embedding：`.local-services/logs/qwen3-embedding.log`

若启动中断，先执行：

```bash
./math-tutor-agent/scripts/dev-stack check
./math-tutor-agent/scripts/dev-stack status
./math-tutor-agent/scripts/dev-stack logs
```

若网页请求失败，可从响应头复制 `X-Request-ID`，再在 `app.log` 中检索相同的 `request_id`，查看请求、Agent 和依赖调用组成的完整链路。日志默认不会记录题目全文、学生作答、模型 Prompt、Token、密码或 API Key。

## 相关代码

- [统一开发服务脚本](../../../scripts/dev-stack)
- [本地服务管理脚本](../../../scripts/local-services)
- [本地服务安装脚本](../../../scripts/setup-local-services)
- [Qwen Embedding 服务](../../../services/qwen3_embedding/server.py)
- [后端应用入口](../../../app/main.py)
