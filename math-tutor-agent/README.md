# 数学引导 Agent

面向大学生高等数学指导的多 Agent 工程。MVP 固定为 `math + university`，从文字与图片题目开始；模型、OCR、语音、检索和学习记录通过可替换适配器接入。

## 设计目标

- 让学生先思考，按卡点逐级提示，必要时再展开完整解法。
- 将教学流程、模型调用、会话状态和外部能力拆开，避免把所有规则塞进一个提示词。
- 保持模型供应商可替换，并让每次回答可校验、可追踪。

## 目录

- [`docs/README.md`](./docs/README.md)：文档总入口、主题关系、推荐阅读顺序和维护规则。
- `docs/00-overview/`：项目总览、当前待办和首版验收。
- `docs/agent/`：12 个专职 Agent 的职责、输入输出和协作架构。
- `docs/module/`：系统架构、平台、教学、题库、RAG、知识内容、API、多模态、隐私和评估模块。
- `tests/README.md`：领域状态、MySQL Repository、Redis 幂等与锁的自动化测试及隔离配置。
- `evals/`：冻结的高难题、题目生成及隔离 RAG 检索评估数据和 manifest。
- `app/mcp_tools/README.md`：数学验证、相似题与复习计划工具说明。
- `app/`：Python 服务端骨架，按 API、领域逻辑、模型适配器和配置拆分。

## 启动

建议 Python 3.11+。完成 `docs/module/运行基础设施模块/LOCAL_SERVICES.md` 的首次准备后，从仓库根目录使用统一命令：

```bash
./math-tutor-agent/scripts/dev-stack start
```

该入口检查必要配置，按 MySQL、Redis、Qdrant、Embedding、迁移、API、前端的固定顺序启动，并等待每一项就绪。`alembic upgrade head` 会使用 `.env` 中的 `DATABASE_URL` 创建或升级 MySQL 表。生产发布前请先阅读 `docs/module/运行基础设施模块/MIGRATIONS.md`，尤其是备份、迁移审核和回滚限制。

首次使用先调用 `POST /v1/auth/register` 注册账号，完成邮件中的邮箱验证后，再通过 `POST /v1/auth/token` 登录。所有辅导接口都要求 Bearer Token。生产环境必须替换 `AUTH_JWT_SECRET`、启用 Secure Refresh Cookie、配置 SMTP 并保持 Redis 限流开启，身份、授权与限流规则见 `docs/module/身份认证与权限模块/AUTHORIZATION.md` 和 `docs/module/身份认证与权限模块/RATE_LIMITING.md`。

当前原型提供大学高数辅导闭环：创建会话、题目确认、卡点诊断、三级提示、完整讲解、完成总结、MySQL 错题记录与家长报告。MySQL Repository 将会话、消息、Agent 产物和学习记录写入规范化表；Redis 用于同一会话的分布式锁、每轮请求幂等和热点会话缓存。知识目录默认从“函数、极限与连续”开始；配置可用的 DeepSeek 或 Gemini 后处理高数题。模型或校验不可用时会明确降级，不会编造答案。

## API

- `GET /v1/health/live`：进程存活检查，不访问外部依赖。
- `GET /v1/health/ready`：检查 MySQL、Redis 和 LLM Provider 是否可以接收新流量。
- `POST /v1/auth/register`：注册学生或家长账号。
- `POST /v1/auth/token`：登录并取得短期 Bearer Token。
- `POST /v1/auth/refresh`：轮换 HttpOnly Refresh Token 并取得新 Access Token。
- `POST /v1/auth/email-verification/confirm`：确认注册邮箱。
- `POST /v1/auth/password/forgot`：发送密码重置邮件。
- `POST /v1/auth/password/change`：登录后修改密码并撤销旧会话。
- `GET /v1/auth/me`：读取当前账号。
- `POST /v1/auth/guardian-links`：家长发起学生关联申请。
- `POST /v1/tutoring/sessions`：创建辅导会话。
- `GET /v1/tutoring/sessions`：按更新时间读取当前学生的会话历史，供首页恢复未完成学习。
- `POST /v1/tutoring/problem-images`：上传 JPEG、PNG 或 WebP 题目图片并建立处理状态。
- `GET /v1/tutoring/problem-images/{asset_id}`：查询当前学生题目图片的处理状态。
- `GET /v1/llm/models`：读取用户可选择的 DeepSeek、Gemini 及其他已注册模型。
- `GET /v1/tutoring/sessions/{session_id}`：恢复会话。
- `GET /v1/tutoring/sessions/{session_id}/trace`：读取 Harness 的 Agent 运行轨迹。
- `POST /v1/tutoring/sessions/{session_id}/turns`：提交学生作答、提示或完整讲解请求。
- `POST /v1/tutoring/sessions/{session_id}/turns/stream`：使用 SSE 接收处理进度、增量回复和完整 `TurnResponse`。
- `POST /v1/tutoring/sessions/{session_id}/content-issues`：学生报告题目、答案、提示或歧义问题，并触发内容重新验证。
- `POST /v1/admin/generation/jobs`：从一批可信母题幂等创建并执行候选变式题生成批次。
- `POST /v1/admin/generation/jobs/{job_id}/run`：执行或恢复已有候选题生成任务。
- `GET /v1/admin/generation/jobs/{job_id}`：查看批次逐位置结果、失败原因和累计用量。
- `GET /v1/admin/generation/quality-report`：按批次、知识点或时间范围统计题库生成质量。
- `GET /v1/curriculum/knowledge-graph`：读取大学高数知识点目录及递归先修关系，默认返回 `UC.C1`。
- `GET /v1/admin/generation/release-gate`：检查错误自动准入率和最小样本门槛，决定是否阻断上线。
- `PUT /v1/admin/revalidation/policies/{policy_key}`：配置已批准题目的周期复核范围与版本。
- `POST /v1/admin/revalidation/runs/run-due`：执行到期的 AI 交叉复核和工具批量重验。
- `GET /v1/admin/revalidation/runs/{run_id}`：查看复核批次、逐题结果和证据引用。
- `POST /v1/admin/human-reviews/queue/refresh`：为隔离内容和高价值内容建立人工抽检队列。
- `GET /v1/admin/human-reviews/tasks`：教师查看待领取或本人已领取的抽检任务。
- `GET /v1/tutoring/learning-records`：读取真实完成的学习记录。
- `GET /v1/tutoring/review-tasks`：读取已到期、未来或全部间隔复习任务。
- `POST /v1/tutoring/review-tasks/{learning_record_id}/attempts`：记录复习结果并生成下一次复习时间。
- `GET /v1/tutoring/parent-report`：按实际记录生成家长报告数据。

HTTP API 和 CLI 都通过 `MathTutorAgentHarness` 运行。可信 CLI 入口需要显式指定已经存在的学生账号，例如 `math-tutor-harness "求 x→0 时 (e^x-1-x)/x^2 的极限" --student-id <student_uuid>`。

首批可信母题可先运行 `math-tutor-problem-bank --validate-only` 做离线检查，再运行 `math-tutor-problem-bank` 事务导入 MySQL；完整边界见 `docs/module/题库生产与治理模块/TRUSTED_SEED_IMPORT.md`。

可信母题和生成版本准备好后，可用 `math-tutor-generate create --file generation-request.json` 执行批量变式生成，并用 `math-tutor-generate show <job_id>` 查询完整批次输出；请求格式见 [`可信母题批量变式生成`](./docs/module/题库生产与治理模块/可信母题批量变式生成/README.md)。

知识文档通过带原文件哈希的摄取清单导入。可先运行 `math-tutor-ingest --manifest <清单路径> --validate-only` 查看确定性解析与切片摘要，再去掉 `--validate-only` 事务写入 MySQL；版本和去重规则见 `docs/module/RAG与检索模块/DOCUMENT_INGESTION.md`。

启用 Qdrant 前先配置独立的 Embedding Provider，再运行 `math-tutor-vector-store ensure-collection` 创建或校验集合和 payload indexes。该命令不自动同步 MySQL 内容，完整说明见 `docs/module/RAG与检索模块/QDRANT_VECTOR_STORE.md`。

生产检索推荐启用混合 Provider：

```dotenv
RAG_ENABLED=true
RAG_PROVIDER=hybrid
```

它会合并 MySQL 中文关键词召回和 Qdrant 语义向量召回，再按题目条件、求解目标和解法结构重排；任一路暂时不可用时，另一条链路仍可降级返回结果。

数据库结构升级到当前 head 后，可以查看并同步生产索引：

```bash
math-tutor-index status
math-tutor-index sync --limit 25
```

## 前端联调

在仓库根目录复制 `.env.example` 为 `.env`，然后启动 Vite。默认前端连接 `http://localhost:8000/v1`。图片与语音仍是后续 Provider，不影响文字版启动。
