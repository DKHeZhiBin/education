# 数学引导 Agent

面向教育产品的数学辅导 Agent 独立工程。当前阶段先明确系统边界与模块接口，默认从文字题目开始；图片识别、语音和学习记录通过可替换适配器接入。

## 设计目标

- 让学生先思考，按卡点逐级提示，必要时再展开完整解法。
- 将教学流程、模型调用、会话状态和外部能力拆开，避免把所有规则塞进一个提示词。
- 保持模型供应商可替换，并让每次回答可校验、可追踪。

## 目录

- `docs/architecture.md`：参考 MindBridge 文档风格整理的运行架构、组件职责、数据流、存储与部署边界。
- `docs/SYSTEM_DESIGN.md`：多 Agent 教学流程、各 Agent 输入输出、接口草案和迭代路径。
- `docs/REFERENCE_MAPPING.md`：`homework-companion` Skill 及其引用在产品中的映射与调整。
- `docs/HARNESS.md`：Harness 运行入口、结果合约、预算、trace 与适配方式。
- `docs/DATA_MODEL.md`：API、领域、Harness 数据对象及 MySQL 8.0 表模型。
- `docs/REDIS_DESIGN.md`：采用 Redis 的原因、锁/幂等/缓存键、TTL 与故障降级策略。
- `docs/REDIS_FAILURE_POLICY.md`：生产环境 Redis 快速失败与 MySQL 回源的分级决策矩阵。
- `docs/HEALTH_CHECKS.md`：进程存活检查，以及 MySQL、Redis、LLM Provider 就绪检查。
- `docs/PROBLEM_UNDERSTANDING.md`：题型、条件、目标、歧义识别及交互式澄清流程。
- `docs/SOLUTION_ANALYSIS.md`：多解法、推荐路线、关键突破口和解法一致性规则。
- `docs/SOLUTION_VERIFICATION.md`：SymPy 确定性校验、混合复核和覆盖边界。
- `docs/PROOF_VERIFICATION.md`：非程序化证明题的六维审查、阻断规则和置信度上限。
- `docs/SOLUTION_REVISION.md`：校验失败后的定向修订、停止条件、最大次数和预算关系。
- `docs/HINT_STRATEGY.md`：方向、关键关系、局部步骤、完整讲解的四级策略和答案展示门槛。
- `docs/LEARNER_STATE.md`：本轮证据、有效尝试、掌握点、误区假设和固定标签过滤规则。
- `docs/EVALUATION.md`：高难题评估集的来源、审核边界、防泄漏、评分维度和版本规则。
- `docs/FIXED_EVALUATION_SUITES.md`：固定题目生成评估、隔离 RAG 检索评估、指标和版本规则。
- `docs/GENERATION_QUALITY_METRICS.md`：题意、答案、确定性覆盖、重复拦截和自动准入统计口径。
- `docs/RAG_QUALITY_METRICS.md`：检索召回、重排、答案依据和引用正确性评估口径。
- `docs/PERIODIC_REVALIDATION.md`：已批准题目的定期 AI 交叉复核、工具批量重验和失败隔离流程。
- `docs/RAG_DESIGN.md`：可关闭、可替换的知识检索 Provider、领域合约、装配和故障策略。
- `docs/QDRANT_VECTOR_STORE.md`：Qdrant 集合、Embedding Provider、payload 合约、过滤和就绪检查。
- `docs/PRODUCTION_INDEXING.md`：MySQL 关键词生产索引和 `approved` 内容的 Qdrant 同步流程。
- `docs/INDEX_LIFECYCLE.md`：题目退役、重新验证和版本更新后的索引删除与重建流程。
- `docs/LOCAL_SERVICES.md`：本地 MySQL、Qdrant 的版本、地址与启停命令。
- `docs/RAG_DATA_MODEL.md`：来源引用、教材版本、知识文档、切片、题目和题解的数据对象与 MySQL 映射。
- `docs/RAG_SOURCES.md`：RAG 首批允许来源、许可边界、题解准入和禁止导入清单。
- `docs/TRUSTED_SEED_IMPORT.md`：ORCCA 首批可信母题、SymPy 校验与幂等导入流程。
- `docs/DOCUMENT_INGESTION.md`：RAG 文档解析、公式规范化、切片、去重与版本管理流程。
- `docs/QUESTION_GENERATION_JOB.md`：候选题生成 Job 的输入输出、预算、幂等与批次状态机。
- `docs/QUESTION_VARIATION_AGENT.md`：可信母题变式生成、禁答规则和只写 candidate 的持久化边界。
- `docs/PROBLEM_CONDITION_CHECK.md`：候选题歧义、条件、定义域、解数量语义和学段适配检查。
- `docs/INDEPENDENT_SOLVING.md`：隔离输入、独立题解、输入指纹和 `solution_independence` 证据。
- `docs/QUADRATIC_SYMPY_VERIFICATION.md`：一元二次方程求解、代回、根完整性、定义域和边界条件验证。
- `docs/NUMERIC_VERIFICATION.md`：独立 Decimal 数值抽样、有限整数域穷举和第二类准入证据。
- `docs/DUPLICATE_DETECTION.md`：文本、公式 AST、条件结构和解法结构四层重复检测。
- `docs/EVALUATION_LEAKAGE_DETECTION.md`：冻结评估集完整性校验、题面相似度与生产隔离规则。
- `docs/INDEPENDENT_AI_REVIEW.md`：候选答案、独立答案、工具证据和教学标签的独立 AI 复核规则。
- `docs/AUTOMATIC_ADMISSION_GATE.md`：确定性证据优先的自动批准、修订、隔离和等待规则。
- `docs/CANDIDATE_REVISION.md`：候选题基于明确失败证据的两次修订上限、版本链和完整重验规则。
- `docs/VERIFICATION_SCOPE_POLICY.md`：证明题与开放题的 partial 覆盖上限、权威证据和隔离规则。
- `docs/GENERATION_AUDIT.md`：生成、检查、验证、复核、修订和状态变化的不可变审计时间线。
- `docs/GENERATION_BATCH_MANAGEMENT.md`：生成批次暂停、恢复、取消、重试和批准内容撤回。
- `docs/CONTENT_TAGGING.md`：年级、知识点、题型、难度来源、教材版本和内容类型标签。
- `docs/KNOWLEDGE_ADMIN.md`：题库管理查询、状态写入、审计详情和并发约定。
- `docs/MIGRATIONS.md`：Alembic 升级、回滚、版本生成和生产发布流程。
- `docs/AUTHORIZATION.md`：JWT 登录、角色权限、家长授权和会话归属规则。
- `docs/RATE_LIMITING.md`：登录、注册和家长关联接口的 Redis/IP/账号组合限流策略。
- `docs/TODO.md`：按优先级维护 MySQL、Redis、RAG、教学能力和部署工作。
- `evals/`：冻结的高难题、题目生成及隔离 RAG 检索评估数据和 manifest。
- `app/mcp_tools/README.md`：数学验证、相似题与复习计划工具说明。
- `app/`：Python 服务端骨架，按 API、领域逻辑、模型适配器和配置拆分。

## 启动

建议 Python 3.11+。复制 `.env.example` 为 `.env`，配置模型地址和密钥后：

```bash
cd math-tutor-agent
python -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

`alembic upgrade head` 会使用 `.env` 中的 `DATABASE_URL` 创建或升级 MySQL 表。生产发布前请先阅读 `docs/MIGRATIONS.md`，尤其是备份、迁移审核和回滚限制。

首次使用先调用 `POST /v1/auth/register` 注册账号，完成邮件中的邮箱验证后，再通过 `POST /v1/auth/token` 登录。所有辅导接口都要求 Bearer Token。生产环境必须替换 `AUTH_JWT_SECRET`、启用 Secure Refresh Cookie、配置 SMTP 并保持 Redis 限流开启，身份、授权与限流规则见 `docs/AUTHORIZATION.md` 和 `docs/RATE_LIMITING.md`。

当前原型提供文字辅导闭环：创建会话、题目确认、卡点诊断、三级提示、完整讲解、完成总结、MySQL 错题记录与家长报告。MySQL Repository 将会话、消息、Agent 产物和学习记录写入规范化表；Redis 用于同一会话的分布式锁、每轮请求幂等和热点会话缓存。内置规则覆盖演示题 `3(x − 2) = 2x + 5`；配置 OpenAI-compatible 模型后可处理开放题目。模型或校验不可用时会明确降级，不会编造答案。

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
- `GET /v1/tutoring/sessions/{session_id}`：恢复会话。
- `GET /v1/tutoring/sessions/{session_id}/trace`：读取 Harness 的 Agent 运行轨迹。
- `POST /v1/tutoring/sessions/{session_id}/turns`：提交学生作答、提示或完整讲解请求。
- `GET /v1/admin/generation/quality-report`：按批次、知识点或时间范围统计题库生成质量。
- `GET /v1/admin/generation/release-gate`：检查错误自动准入率和最小样本门槛，决定是否阻断上线。
- `PUT /v1/admin/revalidation/policies/{policy_key}`：配置已批准题目的周期复核范围与版本。
- `POST /v1/admin/revalidation/runs/run-due`：执行到期的 AI 交叉复核和工具批量重验。
- `GET /v1/admin/revalidation/runs/{run_id}`：查看复核批次、逐题结果和证据引用。
- `GET /v1/tutoring/learning-records`：读取真实完成的学习记录。
- `GET /v1/tutoring/parent-report`：按实际记录生成家长报告数据。

HTTP API 和 CLI 都通过 `MathTutorAgentHarness` 运行。可信 CLI 入口需要显式指定已经存在的学生账号，例如 `math-tutor-harness "3(x - 2) = 2x + 5" --student-id <student_uuid>`。

首批可信母题可先运行 `math-tutor-problem-bank --validate-only` 做离线检查，再运行 `math-tutor-problem-bank` 事务导入 MySQL；完整边界见 `docs/TRUSTED_SEED_IMPORT.md`。

知识文档通过带原文件哈希的摄取清单导入。可先运行 `math-tutor-ingest --manifest <清单路径> --validate-only` 查看确定性解析与切片摘要，再去掉 `--validate-only` 事务写入 MySQL；版本和去重规则见 `docs/DOCUMENT_INGESTION.md`。

启用 Qdrant 前先配置独立的 Embedding Provider，再运行 `math-tutor-vector-store ensure-collection` 创建或校验集合和 payload indexes。该命令不自动同步 MySQL 内容，完整说明见 `docs/QDRANT_VECTOR_STORE.md`。

生产检索推荐启用混合 Provider：

```dotenv
RAG_ENABLED=true
RAG_PROVIDER=hybrid
```

它会合并 MySQL 中文关键词召回和 Qdrant 语义向量召回，再按题目条件、求解目标和解法结构重排；任一路暂时不可用时，另一条链路仍可降级返回结果。

数据库升级到 `20261004_0017` 后，可以查看并同步生产索引：

```bash
math-tutor-index status
math-tutor-index sync --limit 25
```

## 前端联调

在仓库根目录复制 `.env.example` 为 `.env`，然后启动 Vite。默认前端连接 `http://localhost:8000/v1`。图片与语音仍是后续 Provider，不影响文字版启动。
