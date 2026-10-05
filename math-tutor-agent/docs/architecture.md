# 数学辅导 Agent 系统架构

本文描述 `math-tutor-agent` 的当前运行架构。项目采用 Harness 驱动的模块化单体：FastAPI 和 CLI 是入口适配器，`MathTutorAgentHarness` 统一管理会话生命周期、预算、编排、trace、降级与持久化。

## 1. 系统边界与技术栈

| 层次 | 设计 |
| --- | --- |
| 用户界面 | 仓库外的 React + TypeScript 教育产品前端 |
| Web/API | FastAPI、Uvicorn/ASGI、REST；首版同步 HTTP，确认流式需求后增加 SSE |
| 应用服务 | 薄服务层 + `MathTutorAgentHarness` |
| Agent 协作 | 一个受控的教学编排器调用职责单一的专职 Agent，通过结构化 artifact 交接 |
| 持久化 | SQLAlchemy Repository + MySQL 8.0；会话聚合写入规范化业务表 |
| 运行协同 | Redis：分布式会话锁、请求幂等、热点会话缓存和认证限流；MySQL 仍是事实数据源 |
| 账号通知 | 可替换 SMTP Email Provider：邮箱验证与密码重置链接 |
| 模型接入 | 统一 LLM Provider 接口，允许 OpenAI-compatible API、本地模型或 Mock Provider |
| 数学工具 | 可选 MathVerifier 适配器（CAS/数值计算）；工具受服务端白名单和超时控制 |
| 多模态 | 可选 OCR、ASR、TTS Provider；文字辅导不依赖特定云厂商 |
| 部署 | 首版单体 API 服务；数据库可独立部署，不拆微服务 |

## 2. 容器与组件视图

```mermaid
flowchart LR
    UI[React 教育产品] -->|HTTP / SSE| API[FastAPI]
    API --> Auth[邮箱验证、Access/Refresh Token 与家长授权]
    Auth --> Mail[SMTP Email Provider]
    Auth --> DB
    Auth --> Redis
    API --> Service[TutoringService]
    CLI[CLI Adapter] --> Harness[MathTutorAgentHarness]
    Service --> Harness
    Harness --> Runtime[Teaching Orchestrator]
    Harness --> State[Session Repository]
    Harness --> Redis[(Redis)]
    Runtime --> Problem[Problem Understanding Agent]
    Runtime --> Solver[Solution Analysis Agent]
    Runtime --> Verify[Solution Verification Agent]
    Runtime --> Diagnose[Learner Diagnosis Agent]
    Runtime --> Tutor[Hint and Teaching Agent]
    Runtime -.完成后.-> Record[Learning Record Agent]
    Problem --> Input[Text / Optional OCR Adapter]
    Solver --> Math[Optional MathVerifier]
    Verify --> Math
    Runtime --> LLM[LLM Provider]
    State --> DB[(MySQL 8.0)]
    Record --> DB
```

目标是一个可独立部署的模块化单体：Agent 角色在代码层分开，但通过进程内编排服务协作。只有在负载、团队边界或独立伸缩需求出现后，才考虑把模型调用、OCR 或异步报告拆成服务。

## 3. 代码模块职责

目标目录结构：

```text
app/
  api/                 # HTTP 路由、请求/响应 DTO、鉴权依赖
  core/                # 配置、日志、错误类型、生命周期
  domain/              # 会话状态、题目/解答/学习记录等领域模型
  services/            # 将 HTTP 请求映射为 Harness 调用
  harness/             # 统一运行入口、结果合约、预算、trace、依赖装配
  agents/              # understanding / solver / verifier / diagnosis / tutor / record
  providers/           # LLM、数学工具、OCR/ASR/TTS 的可替换适配器
  mcp_tools/           # 数学验证、相似题和复习计划 MCP Server
  repositories/        # 会话、消息、Agent artifact、学习记录存储接口与实现
  prompts/             # 按 Agent 管理的指令模板与输出 schema
```

HTTP、CLI 或未来的 OpenClaw 入口都不得直接调用具体 Agent。它们通过 Harness 获得统一的 `HarnessRunResult`；具体 Agent 也不直接依赖彼此实现。

## 4. 在线辅导数据流

1. 客户端携带 Bearer Token 创建会话或提交一轮消息；API 校验账号状态、角色、字段和会话归属。
2. `TutoringService` 将请求交给 `MathTutorAgentHarness`。
3. Harness 创建 `run_id`、检查调用预算、读取会话并调用 Teaching Orchestrator。
4. 新题路径：题目理解 Agent 产出 `ProblemSpec 2.0`，记录题型证据、条件来源、求解目标和分级歧义；存在阻断歧义时立即返回澄清问题并暂停解题，补充后重新理解题目。
5. 题意明确后，解题分析 Agent 生成 `SolutionPlan 2.1`，比较可靠解法并提取关键突破口；解答校验 Agent 优先用安全 SymPy 工具独立求解、比较步骤、代回答案并检查解集完整性。证明题走六维结构化复核并固定为部分覆盖，最终产出 `VerificationReport 2.1`。可修订失败默认最多退回两次，每版必须重新校验，达到上限后停止并禁止使用未通过解法。
6. 提示教学 Agent 根据经校验方案、当前阶段和学生历史，生成单轮 `TutorReply`。学生回答后进入诊断和下一轮提示。
   提示按方向、关键关系、局部步骤、完整讲解四级递进；前三个等级只接收裁剪后的教学上下文，第四级还要求明确请求及有效尝试或既有三级提示。
7. 每次 Agent 输出先做 schema、权限和状态校验；Harness 收集 artifact、置信度与耗时形成 trace。
8. 会话完成时按产品策略调用学习记录 Agent，持久化错因、知识点和复习建议。
9. Harness 保存会话并返回统一运行结果；API 返回回复、`run_id`、trace、耗时和降级状态。

```mermaid
sequenceDiagram
    participant U as React 客户端
    participant API as FastAPI
    participant S as TutoringService
    participant H as MathTutorAgentHarness
    participant O as Teaching Orchestrator
    participant P as 理解 Agent
    participant A as 解题分析 Agent
    participant V as 解答校验 Agent
    participant D as 学情诊断 Agent
    participant T as 提示教学 Agent
    participant DB as Repository
    U->>API: 创建会话 / 提交本轮
    API->>S: 请求 DTO
    S->>H: start_session / run_turn
    H->>DB: 读取会话
    H->>O: run_id + 输入 + 会话快照
    O->>P: 仅新题/题意变化时调用
    P-->>O: ProblemSpec 或澄清请求
    O->>A: 题意明确后生成解题方案
    A-->>O: SolutionPlan
    O->>V: 独立校验
    V-->>O: VerificationReport
    O->>D: 学生后续作答时诊断卡点
    D-->>O: LearnerState
    O->>T: 教学任务 + 已校验依据
    T-->>O: TutorReply
    O-->>H: 回复 + 状态迁移 + artifact
    H->>DB: 保存完整会话
    H-->>S: HarnessRunResult
    API-->>U: 回复、阶段、下一步
```

## 5. Agent 协作模型

Agent 通过共享的、单轮运行上下文交换类型化 artifact。它们不直接自由调用其他 Agent；调用顺序、预算、重试和终止由 Orchestrator 控制。

| Agent | 输入 | 输出 | 调用条件 |
| --- | --- | --- | --- |
| TeachingOrchestrator | 用户输入、会话状态 | 有序任务计划、最终采纳结果 | 每轮必经；作为控制面 |
| ProblemUnderstandingAgent | 新题文字/附件解析结果 | `ProblemSpec` 或澄清问题 | 新题或题意变化 |
| SolutionAnalysisAgent | 已确认的 `ProblemSpec` | `SolutionPlan` | 首轮分析或校验要求修订 |
| SolutionVerificationAgent | `ProblemSpec` + `SolutionPlan` | `VerificationReport` | 给提示前；修订后再次校验 |
| LearnerDiagnosisAgent | 学生本轮回答 + 已校验解法上下文 | `LearnerState 2.0` | 学生提交尝试或表达卡点 |
| HintTeachingAgent | 校验结果 + 学情 + 提示等级策略 | `TutorReply` | 每个需要面向学生回复的辅导轮次 |
| LearningRecordAgent | 完成的会话摘要和学情结果 | `LearningRecord` | 完成、收藏或复习触发时 |

推荐的 artifact 合约：`ProblemSpec`、`SolutionPlan`、`VerificationReport`、`LearnerState`、`TutorReply`、`LearningRecord`。每个 artifact 带 `session_id`、`turn_id`、`schema_version`、来源 Agent 和置信度。完整内部推理不暴露给客户端；对学生只展示经过整理的解释和必要依据。

## 6. 会话状态与数据存储

首版教学状态建议：`collecting`、`clarifying`、`diagnosing`、`hinting`、`checking_attempt`、`explaining`、`completed`。状态迁移由领域服务校验，不由模型任意指定。

| 数据 | 存储 | 用途 |
| --- | --- | --- |
| 用户与授权关系 | MySQL；邮箱验证、Access/Refresh Token、学生所有权与家长显式授权 | 身份认证、令牌轮换、学生与家长授权关系 |
| 会话、消息、artifact 与 run trace | MySQL Repository | 恢复对话、呈现历史、审计和定位 Agent 问题 |
| 学习记录与错题 | MySQL Repository | 个性化复习和学习报告 |
| 热点会话快照 | Redis，默认 TTL 1 小时 | 降低连续辅导过程中的数据库读取延迟 |
| 本轮幂等结果 | Redis，默认 TTL 24 小时 | 使用 `client_turn_id` 防止重复模型调用和重复写入 |
| 会话分布式锁 | Redis，默认 TTL 120 秒 | 多副本下让同一会话的状态更新保持串行 |
| 上传图片/音频 | 对象存储适配器（后续） | 原始附件不直接塞入关系数据库 |

MySQL 是正式数据层目标，Redis 是可降级的运行协同层。采用 Redis 是因为会话锁、短期幂等结果和热点缓存需要跨实例共享、原子操作及自动过期；这些数据不适合在模型调用期间通过长数据库事务维护。Redis 不存唯一副本，读取失败时回源 Repository，写入失败时正式学习数据仍以 MySQL 为准。键设计、TTL 和故障策略见 `docs/REDIS_DESIGN.md`。

## 7. API 与客户端集成

- `GET /v1/health/live`：不访问外部依赖的进程存活检查。
- `GET /v1/health/ready`：并行检查 MySQL、Redis 和可配置为必需依赖的 LLM Provider。
- `POST /v1/tutoring/sessions`：创建会话并提交初始题目。
- `POST /v1/tutoring/sessions/{session_id}/turns`：提交学生回答、追问或提示请求。
- `GET /v1/tutoring/sessions/{session_id}`：读取会话状态与历史消息。
- `GET /v1/tutoring/sessions/{session_id}/trace`：读取按 `run_id` 标识的 Agent 调用轨迹。
- 后续可加 `POST /v1/tutoring/sessions/{session_id}/complete` 及独立的学习记录查询接口。

客户端只依赖稳定的 REST DTO，不依赖某个 Agent 名称或提示词。`TutorReply` 返回 `action`、`text`、`hint_level`、`hint_stage`、`can_show_full_solution`、可选 `understanding_check` 和 `session_status`。SSE 事件只负责传输过程，不改变领域接口。

提交一轮消息时，客户端应生成并复用 `client_turn_id`。网络超时后的重试必须携带相同值，服务端才能返回第一次运行结果；新的学生表达必须使用新的值。

## 8. 部署与外部依赖

首版采用单体 API 部署：FastAPI 应用内运行 API、应用服务和多 Agent 编排；模型服务及数据库作为外部依赖。MySQL 表结构由 Alembic 版本化管理，发布应用前执行 `alembic upgrade head`。开发时可用 Mock Provider 验证流程，避免必须持有云密钥才能启动。环境变量集中在配置模块，密钥不写入仓库和日志。

外部能力均以 Provider 接口接入：

- LLM Provider：生成结构化 Agent 输出。
- MathVerifier：可选代数/数值检查；不可用时将校验局限明确传入回复策略。
- MCP Tools：以 stdio 或 Streamable HTTP 暴露确定性数学验证与复习调度能力。
- OCR/ASR/TTS Provider：图片/语音输入输出；没有这些服务时文字辅导继续工作。
- KnowledgeRetriever Provider：按需提供带引用的教材知识上下文；默认关闭，可替换后端且不阻断原教学链路。
- Repository：可替换存储实现。

具体模型供应商、数据库实例和云部署平台在成本、账号与部署环境明确后再确定，不预设腾讯云。

## 9. 运行边界与扩展注意事项

- 多 Agent 是应用内的职责分工与受控调用，不代表首版就拆成多个微服务或多个长期运行的自治 Agent。
- 解答校验应尽量使用独立方法或工具；同一模型自我复述不能作为强正确性证明。
- Agent 只接收完成任务所需的最小上下文；控制最大轮次、模型调用数、超时和 token 预算。
- `LearnerState` 只引用学生本轮消息中的证据；没有证据时记录不确定性并追问，不把一次表现固化为能力或人格标签。
- 模型输出均视为不可信输入：schema 校验、状态校验、长度限制和工具参数白名单不可省略。
- 高难证明题无法完全程序化判定时，必须按目标对应、条件使用、逻辑连续性、定理适用条件、分类完整性和结论闭合报告证据。单模型复核固定为部分覆盖且通过置信度不高于 0.74，不能把“未发现错误”说成“已证明正确”。
- Redis 已承载会话锁、幂等键、热点会话缓存，以及认证接口的 IP/账号组合限流；异步任务状态可在需要时复用独立键空间接入。
- 图片与语音引入后，需增加上传大小/格式限制、内容生命周期和隐私策略。
- 家长解除关联后不得继续读取学生的新报告。
- 不将孩子真实姓名、学校、住址或电话写入 Agent artifact、trace 或日志。
- 数据库备份和只读副本必须采用与主库相同的访问控制和删除策略。

## 10. 一致性与并发

- `learning_sessions.version` 参与 Repository 的原子条件更新；成功后版本加一，冲突时回滚消息、Agent 轨迹和学习记录的同一事务，并清除旧 Redis 会话快照。
- `client_turn_id` 保证客户端重试不会重复创建消息和 Agent run。
- 创建学习记录时，以 `session_id` 唯一约束保证幂等。
- 周报以学生、周期类型和日期范围唯一，重新生成时更新现有草稿。
- Harness 开始时写入 `agent_runs.running`；成功后在同一事务写入最终状态。超时回收任务可将长期 `running` 标记为 `failed`。

## 11. Repository 边界

建议将当前单一 `SessionRepository` 拆为以下接口：

```text
SessionRepository
MessageRepository
AgentRunRepository
LearningRecordRepository
ReportRepository
MediaAssetRepository
```

Harness 通过 Unit of Work 使用这些接口，保证一次运行的数据原子提交。Agent 不得直接持有数据库连接；模型 Provider 也不得读写业务表。

## 12. 迁移顺序

1. 引入 MySQL 连接配置与 Alembic 初始迁移，建立完整业务表。（已完成）
2. 使用 MySQL Repository 将会话聚合写入 `learning_sessions`、`session_messages`、`agent_runs`、`agent_run_steps` 和 `agent_artifacts`。（已完成）
3. 接入 Redis 会话锁、幂等结果和热点缓存。（已完成）
4. 在 Repository 更新路径启用 `learning_sessions.version` 乐观锁和 HTTP 409 冲突处理。（已完成）
