# 项目技术栈与学习指南

本文记录大学高数 AI 辅导系统使用的主要技术，并说明每项技术在项目中解决什么问题、代码入口在哪里，以及适合怎样学习。

这不是依赖清单的简单复制。阅读时应把技术放回业务流程中理解：学生提交题目后，前端通过 API 调用辅导服务，Harness 编排多个 Agent，MySQL 保存长期数据，Redis 处理短期协调，RAG 从 MySQL 和 Qdrant 检索教学内容，最后通过 REST 或 SSE 返回前端。

## 目录

1. [技术栈总览](#1-技术栈总览)
2. [前端技术](#2-前端技术)
   - [React](#21-react)
   - [TypeScript](#22-typescript)
   - [Vite](#23-vite)
   - [React Router](#24-react-router)
   - [MathLive 与 LaTeX](#25-mathlive-与-latex)
3. [后端与 API 技术](#3-后端与-api-技术)
   - [Python](#31-python)
   - [FastAPI](#32-fastapi)
   - [Uvicorn](#33-uvicorn)
   - [Pydantic 与 Pydantic Settings](#34-pydantic-与-pydantic-settings)
   - [HTTPX](#35-httpx)
   - [SSE](#36-sse)
4. [数据与持久化技术](#4-数据与持久化技术)
   - [MySQL](#41-mysql)
   - [SQLAlchemy](#42-sqlalchemy)
   - [Repository 模式](#43-repository-模式)
   - [Alembic](#44-alembic)
   - [Redis](#45-redis)
5. [AI、Agent 与 Provider](#5-aiagent-与-provider)
   - [LLM Provider](#51-llm-provider)
   - [多 Agent](#52-多-agent)
   - [Harness](#53-harness)
   - [结构化输出](#54-结构化输出)
   - [MCP](#55-mcp)
6. [RAG 与向量检索](#6-rag-与向量检索)
   - [Embedding](#61-embedding)
   - [Qdrant](#62-qdrant)
   - [RAG](#63-rag)
   - [混合检索](#64-混合检索)
7. [数学验证与多模态](#7-数学验证与多模态)
   - [SymPy](#71-sympy)
   - [数值验证](#72-数值验证)
   - [OCR](#73-ocr)
   - [ASR 与 TTS](#74-asr-与-tts)
8. [安全与运行保障](#8-安全与运行保障)
9. [建议学习顺序](#9-建议学习顺序)
10. [常见概念速查](#10-常见概念速查)
11. [维护规则](#11-维护规则)

## 1. 技术栈总览

```text
学生端 React               知识管理端 React
       │                         │
       └──────── HTTP / SSE ─────┘
                     │
                FastAPI API
                     │
              应用服务与 Harness
                     │
          多 Agent 编排与 Provider
             ┌───────┼────────┐
             │       │        │
           MySQL   Redis    LLM Provider
             │                │
       FULLTEXT 检索      DeepSeek / Gemini
             │
       Embedding Provider
             │
           Qdrant
```

| 层次 | 主要技术 | 在项目中的作用 | 当前状态 |
| --- | --- | --- | --- |
| 学生端 | React、TypeScript、Vite、React Router | 学习流程、会话、知识星图、数学输入与公式展示 | 已使用 |
| 管理端 | React、TypeScript、Vite、React Router | 维护目录、知识点、内容、先修关系和数学方法 | 已使用 |
| API | Python、FastAPI、Uvicorn、Pydantic | REST/SSE 接口、参数校验、依赖注入和错误响应 | 已使用 |
| 应用架构 | Service、Repository、Provider、Harness | 分离业务规则、数据访问、外部能力和 Agent 运行控制 | 已使用 |
| 数据库 | MySQL、SQLAlchemy、PyMySQL | 保存用户、会话、知识内容、题库和审计证据 | 已使用 |
| 结构迁移 | Alembic | 版本化管理 MySQL 表、字段、索引和约束 | 已使用 |
| 运行协调 | Redis | 缓存、幂等、分布式锁、限流和 RAG 缓存失效 | 可配置启用 |
| 向量检索 | Qdrant、Qwen3 Embedding | 语义召回、元数据过滤和生产向量索引 | 可配置启用 |
| RAG | MySQL FULLTEXT、Qdrant、RRF、结构重排 | 从批准内容中检索可控的教学上下文 | 可关闭 |
| 大模型 | DeepSeek、Gemini、OpenAI 兼容协议 | Agent 推理、结构化输出、OCR 等模型能力 | 按配置启用 |
| 数学验证 | SymPy、数值验证器 | 独立验证答案、代回结果和部分数学约束 | 已使用 |
| 多模态 | OCR Provider、ASR/TTS Provider | 图片公式识别、语音能力的可替换接口 | OCR 可配置；语音目前为接口 |
| Agent 工具 | MCP | 将受控数学工具和复核工具暴露为标准工具服务 | 已实现入口 |
| 运行保障 | 结构化日志、健康检查、就绪检查、离线评估 | 定位故障并判断服务是否可用 | 已使用 |

依赖版本以以下文件为准：

- [学生端依赖](../../../package.json)
- [知识管理端依赖](../../../knowledge-admin/package.json)
- [后端 Python 依赖](../../pyproject.toml)

## 2. 前端技术

### 2.1 React

React 是组件化 UI 库。项目用它把认证页、首页、知识星图、辅导工作区、提示页和复盘页拆成独立组件。

在本项目中重点学习：

1. 函数组件与 JSX；
2. `useState`、`useEffect` 等 Hook；
3. 页面状态、服务端状态与表单状态的区别；
4. 如何将重复 UI 抽成组件；
5. 异步请求、加载状态和错误恢复。

代码入口：

- [学生端路由](../../../src/app/App.tsx)
- [学习工作区](../../../src/features/learning/LearningWorkspace.tsx)
- [知识星图](../../../src/features/knowledge/KnowledgePlanetPage.tsx)
- [管理端应用](../../../knowledge-admin/src/App.tsx)

### 2.2 TypeScript

TypeScript 在 JavaScript 上增加静态类型。它能在运行前发现字段拼错、接口返回值不一致和组件参数错误。

项目中的典型用途是为 API DTO 建立接口，例如会话、回复、错误响应和上传状态。学习时重点关注：

- `type` 与 `interface`；
- 联合类型；
- 泛型；
- `null` 与可选字段；
- 根据后端 DTO 维护前端类型。

代码入口：[辅导 API 客户端](../../../src/services/tutoring.ts)。

### 2.3 Vite

Vite 是前端开发服务器和构建工具，负责本地热更新、TypeScript 构建和生产资源打包。

常用命令：

```bash
npm run dev
npm run build
npm run preview
```

学生端和管理端是两个独立 Vite 应用，分别运行在不同端口。

### 2.4 React Router

React Router 根据 URL 展示对应页面，并负责参数路由和登录保护。例如：

```text
/learn/:sessionId/diagnosis
/learn/:sessionId/coach
/knowledge/points/:pointCode
``` 

学习重点是嵌套路由、路由参数、重定向、登录保护和刷新后的状态恢复。

### 2.5 MathLive 与 LaTeX

MathLive 提供接近手写习惯的数学输入组件。LaTeX 是数学公式的文本表示，例如：

```latex
\frac{x^2-1}{x-1}
```

项目需要同时处理：

- 学生输入数学表达式；
- Markdown 正文中的行内公式和块级公式；
- API 返回公式后的统一渲染；
- OCR 公式的确认与修改。

代码入口：[数学作答输入器](../../../src/components/MathAnswerComposer.tsx)。

## 3. 后端与 API 技术

### 3.1 Python

后端采用 Python 3.11 以上版本。Python 适合本项目的原因是 AI SDK、数学计算、数据处理和 Web 框架生态集中。

学习重点：

- 类型注解；
- `dataclass` 与 Pydantic Model；
- 异常处理；
- 上下文管理器；
- Protocol 与依赖倒置；
- 包、模块和导入关系。

### 3.2 FastAPI

FastAPI 是 Python Web API 框架，负责：

- 注册 URL 路由；
- 解析请求；
- 调用应用服务；
- 通过 Pydantic 校验输入输出；
- 生成 OpenAPI 和 Swagger 文档；
- 返回普通 JSON 或 SSE 流。

代码入口：

- [FastAPI 应用](../../app/main.py)
- [辅导路由](../../app/api/routes/tutoring.py)
- [认证路由](../../app/api/routes/auth.py)
- [管理端知识路由](../../app/api/routes/admin_curriculum.py)

### 3.3 Uvicorn

Uvicorn 是运行 FastAPI 的 ASGI Server。FastAPI 描述应用逻辑，Uvicorn 负责监听端口、接收 HTTP 请求并调度异步应用。

二者关系可以理解为：

```text
FastAPI = Web 应用
Uvicorn = 运行 Web 应用的服务器
```

### 3.4 Pydantic 与 Pydantic Settings

Pydantic 将不可信的 JSON 输入转换成有类型的 Python 对象，并执行字段约束。Pydantic Settings 则负责从环境变量和 `.env` 加载配置。

它们在项目中承担：

- API DTO；
- Agent 结构化产物；
- 领域状态对象；
- LLM、MySQL、Redis、Qdrant 等配置；
- 输出格式的运行时校验。

代码入口：

- [后端配置](../../app/core/config.py)
- [辅导领域 DTO](../../app/domain/schemas.py)

### 3.5 HTTPX

HTTPX 是 Python HTTP 客户端。本项目通过它调用 LLM、Embedding 和 OCR 服务。

学习重点包括超时、连接错误、HTTP 状态码、认证 Header、重试边界，以及为什么外部请求不能无限等待。

代码入口：[LLM Provider](../../app/providers/llm.py)。

### 3.6 SSE

SSE（Server-Sent Events）允许服务器在一个 HTTP 响应中持续向浏览器推送事件，适合流式显示 Agent 回复。

与 WebSocket 相比，SSE 是服务器到客户端的单向流，协议更简单，也更适合当前的文本生成场景。

代码与文档：

- [SSE 服务端实现](../../app/api/sse.py)
- [SSE 流式回复设计](../module/API与客户端模块/SSE_STREAMING.md)

## 4. 数据与持久化技术

### 4.1 MySQL

MySQL 是关系型数据库，负责保存需要长期存在、具有关系和事务要求的数据：

- 用户、学生和家长身份；
- 辅导会话、消息和学习记录；
- 知识目录、知识点、内容和先修关系；
- 题目、题解、生成批次和验证证据；
- 生产关键词索引和审计记录。

学习重点是表、字段、主键、外键、索引、事务、唯一约束和查询计划。

### 4.2 SQLAlchemy

SQLAlchemy 是 Python 数据库工具包。项目主要使用 ORM 和 Session：

```text
Python Model ↔ SQLAlchemy ↔ SQL ↔ MySQL
```

它负责把 Python 对象映射到表，并提供查询、事务和关系加载能力。

代码入口：

- [数据库连接](../../app/core/database.py)
- [SQLAlchemy Model](../../app/models/)
- [MySQL 会话 Repository](../../app/repositories/mysql_sessions.py)

学习 SQLAlchemy 时不要只学增删改查，还应理解：

- Session 生命周期；
- 事务提交和回滚；
- 懒加载与预加载；
- 乐观锁；
- ORM 查询最终生成的 SQL。

### 4.3 Repository 模式

Repository 将业务代码与具体数据库查询隔开。例如 Harness 只要求“保存会话”，不应关心 SQLAlchemy 怎样更新表。

```text
业务服务 → Repository 接口 → MySQL Repository → SQLAlchemy → MySQL
```

这样可以集中管理事务、查询和数据库异常，也便于以后替换实现。

### 4.4 Alembic

Alembic 管理数据库结构版本。它记录从旧结构升级到新结构的可执行步骤，而不是业务数据备份。

典型工作流：

```bash
alembic current
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

代码与文档：

- [Alembic 配置](../../alembic.ini)
- [迁移目录](../../migrations/)
- [数据库迁移流程](../module/运行基础设施模块/MIGRATIONS.md)

### 4.5 Redis

Redis 是内存键值存储。项目不把它作为长期业务真相源，而用于：

- 热点会话缓存；
- `client_turn_id` 幂等结果；
- 会话分布式锁；
- 登录与注册限流；
- 热门 RAG 查询缓存；
- 知识索引版本变化后的缓存失效。

代码与文档：

- [Redis 运行缓存](../../app/cache/redis_runtime.py)
- [Redis 设计](../module/运行基础设施模块/REDIS_DESIGN.md)
- [Redis 故障策略](../module/运行基础设施模块/REDIS_FAILURE_POLICY.md)

学习 Redis 时要区分缓存、锁、幂等和限流，它们虽然都使用键值数据，但正确性要求不同。

## 5. AI、Agent 与 Provider

### 5.1 LLM Provider

Provider 是对外部服务的适配层。业务 Agent 不直接依赖 DeepSeek 或 Gemini SDK，而依赖统一接口：

```text
Agent → LLM Provider → DeepSeek / Gemini / 其他兼容模型
```

这样可以让用户选择模型，并在未来增加新模型时减少业务代码改动。

学习重点：接口抽象、配置隔离、超时、结构化输出、模型能力差异和降级处理。

代码与文档：

- [LLM Provider 实现](../../app/providers/llm.py)
- [多模型设计](../module/模型服务模块/LLM_PROVIDERS.md)

### 5.2 多 Agent

项目将复杂教学任务拆成不同职责：题目理解、解法分析、解答校验、学情诊断、提示教学和学习记录等。

这些 Agent 不是在后台自由聊天，而是由 Orchestrator 按状态调用，并通过版本化结构对象交接：

```text
ProblemSpec → SolutionPlan → VerificationReport
                              ↓
学生作答 → LearnerState → TutorReply
```

代码与文档：

- [教学 Agent 编排](../../app/agents/tutoring_team.py)
- [Agent 协作架构](../agent/agent协作架构.md)

### 5.3 Harness

Harness 是 Agent 系统的运行外壳。它负责业务 Agent 之外的工程问题：

- 创建 `run_id`；
- 限制 Agent 调用预算和执行时长；
- 加锁与幂等；
- 读取和保存会话；
- 收集运行 artifact 和 trace；
- 处理冲突与降级。

代码与文档：

- [Harness 实现](../../app/harness/math_tutor.py)
- [Harness 设计](../module/系统架构模块/HARNESS.md)

### 5.4 结构化输出

模型生成自由文本很难被程序可靠处理，因此 Agent 先生成约定的 JSON，再通过 Pydantic 校验。结构不合格时，系统可以明确失败或有限重试。

需要理解的核心原则是：

```text
LLM 输出是不可信输入
Schema 校验通过后才能进入下一阶段
```

### 5.5 MCP

MCP（Model Context Protocol）是一种让模型使用外部工具和上下文的标准协议。本项目通过 MCP 暴露受控数学工具和复核工具。

代码入口：[MCP 工具服务](../../app/mcp_tools/server.py)。

## 6. RAG 与向量检索

### 6.1 Embedding

Embedding 将文本转换成一组数字向量。含义相近的文本，其向量在空间中的距离通常更近。

```text
“求函数极限” → [0.12, -0.08, ...]
```

项目通过可替换的 Embedding Provider 调用 Qwen3 Embedding 服务。

代码入口：

- [Embedding Provider](../../app/providers/embeddings.py)
- [本地 Qwen3 Embedding 服务](../../services/qwen3_embedding/server.py)

### 6.2 Qdrant

Qdrant 是向量数据库，用来保存 Embedding 并执行近邻检索。除了向量，它还保存知识点、难度、内容状态和验证版本等 Payload，便于过滤。

代码与文档：

- [Qdrant Vector Store](../../app/vector_store/qdrant.py)
- [Qdrant 检索 Provider](../../app/providers/qdrant_knowledge.py)
- [Qdrant 接入说明](../module/RAG与检索模块/QDRANT_VECTOR_STORE.md)

### 6.3 RAG

RAG 是“先检索，再生成”：

```text
学生问题
   ↓
检索批准的知识和题目
   ↓
组成受长度和提示等级约束的教学上下文
   ↓
交给教学 Agent 生成回复
```

它不能自动保证答案正确。项目还需要内容准入、元数据过滤、结构重排、引用和评估。

### 6.4 混合检索

项目同时使用：

- MySQL FULLTEXT：擅长精确关键词；
- Qdrant：擅长语义相似；
- RRF：融合不同检索器的排名；
- 结构重排：比较题目条件、目标和解法结构。

代码入口：[混合检索 Provider](../../app/providers/hybrid_knowledge.py)。

## 7. 数学验证与多模态

### 7.1 SymPy

SymPy 是 Python 符号数学库，可以处理方程、表达式化简、求导、积分和代数验证。

在本项目中，SymPy 作为独立工具证据，不直接替代教学推理。模型给出答案后，验证器可以独立求解或代回原条件，降低模型自我确认造成的错误。

代码入口：

- [数学 MCP 工具](../../app/mcp_tools/math_tools.py)
- [SymPy 验证器实现](../../app/verifiers/quadratic_sympy.py)
- [通用验证器说明](../module/题库生产与治理模块/SYMPY_VERIFICATION.md)

### 7.2 数值验证

数值抽样或有限穷举是 SymPy 之外的第二类证据。它适合寻找反例和检查多个输入点，但有限抽样通常不能单独证明命题对所有输入成立。

代码入口：[数值验证器](../../app/verifiers/quadratic_numeric.py)。

### 7.3 OCR

OCR 将题目图片转成文本和 LaTeX 公式。项目要求学生确认和修正识别结果，因为数学符号的一处误识别就可能改变整道题。

代码入口：[OCR Provider](../../app/providers/ocr.py)。

### 7.4 ASR 与 TTS

- ASR：把语音转换成文字；
- TTS：把文字转换成语音。

当前项目已经定义可替换 Provider 接口，但默认实现为未配置状态，不应把它理解为已经接入了具体云语音服务。

代码入口：[语音 Provider 接口](../../app/providers/speech.py)。

## 8. 安全与运行保障

### 8.1 JWT 与密码哈希

JWT 用于携带登录身份，服务端仍需检查账号状态、角色和资源归属。密码通过 Argon2 哈希保存，不能以明文或可逆加密形式存储。

代码入口：

- [安全工具](../../app/core/security.py)
- [身份认证服务](../../app/services/auth.py)

### 8.2 限流

限流控制单位时间内允许的请求数量。登录和注册需要组合 IP 与账号维度，防止暴力尝试，同时避免一个共享 IP 影响所有用户。

代码入口：[限流实现](../../app/security/rate_limit.py)。

### 8.3 日志

日志用于回答“发生了什么、在哪个请求中发生、影响了哪个会话”。日志不能记录密码、Token、完整 API Key 或不必要的学生隐私。

代码与文档：

- [日志配置](../../app/core/logging.py)
- [日志系统说明](../module/运行基础设施模块/LOGGING.md)

### 8.4 健康检查与就绪检查

- 存活检查：进程是否还在运行；
- 就绪检查：MySQL、Redis、Qdrant、Embedding 和 LLM 等必要依赖是否能工作。

代码入口：[就绪检查服务](../../app/services/readiness.py)。

## 9. 建议学习顺序

不要同时学习全部技术。建议按照一次真实请求经过的路径逐层学习。

### 阶段一：看懂学生端

1. JavaScript 基础；
2. TypeScript 类型；
3. React 组件和 Hook；
4. React Router；
5. `fetch`、HTTP 和 JSON；
6. MathLive 与 LaTeX。

练习：从学生点击“发送”开始，沿着 [辅导 API 客户端](../../../src/services/tutoring.ts) 找到请求 URL、请求 DTO 和返回 DTO。

### 阶段二：看懂 API

1. Python 类型注解；
2. FastAPI 路由；
3. Pydantic 校验；
4. Service 分层；
5. HTTP 状态码和统一错误；
6. SSE。

练习：从 [辅导路由](../../app/api/routes/tutoring.py) 找到对应 Service，再跟到 Harness。

### 阶段三：看懂数据层

1. SQL 与 MySQL；
2. SQLAlchemy Model；
3. Session 与事务；
4. Repository；
5. Alembic；
6. Redis 缓存、锁和幂等。

练习：选择一个简单字段，依次观察领域对象、ORM Model、Repository 和迁移文件怎样配合。学习阶段不要直接修改生产数据。

### 阶段四：看懂 AI 工程

1. LLM 请求和结构化输出；
2. Provider 模式；
3. Agent 职责拆分；
4. Orchestrator 与状态机；
5. Harness 的预算、幂等和追踪；
6. SymPy 独立验证。

练习：选择一轮辅导 trace，判断每个 artifact 是哪个 Agent 生成、经过什么 schema 校验、怎样影响下一状态。

### 阶段五：看懂 RAG

1. Embedding；
2. 向量相似度；
3. Qdrant collection 与 payload；
4. 关键词检索；
5. 混合召回和重排；
6. 引用、缓存与离线评估。

练习：用同一条查询分别观察关键词结果、向量结果和最终重排结果，解释名次变化的原因。

## 10. 常见概念速查

| 概念 | 简单解释 |
| --- | --- |
| Framework | 提供应用运行骨架，例如 FastAPI |
| Library | 被业务代码调用的功能集合，例如 SymPy |
| ORM | 在对象与关系表之间建立映射 |
| Migration | 数据库结构的版本化升级步骤 |
| Repository | 封装数据读写的边界 |
| Provider | 封装可替换外部服务的边界 |
| Cache | 保存可重新生成的短期数据以减少耗时 |
| Idempotency | 同一请求重复执行时仍只产生一次业务结果 |
| Embedding | 将内容映射成可比较的数值向量 |
| Vector Database | 保存和检索向量的数据库 |
| RAG | 先检索可信上下文，再让模型生成结果 |
| Agent | 承担一个明确职责的模型驱动组件 |
| Orchestrator | 决定 Agent 调用顺序和状态迁移 |
| Harness | 管理 Agent 运行预算、持久化、幂等、锁和追踪的工程外壳 |
| DTO | API 或模块边界上传递的数据结构 |
| SSE | 服务器持续向浏览器推送事件的单向 HTTP 流 |

## 11. 维护规则

1. 引入新技术时，先写清它解决的问题，不因流行而增加依赖。
2. 在表格中标明“已使用、可配置、仅接口或计划中”。
3. 同步补充真实代码入口，避免文档变成概念百科。
4. 删除技术或替换 Provider 时，同步更新本页和相应模块文档。
5. 版本号以依赖清单和锁文件为准，本页主要记录职责和学习路径。
6. 技术栈文档不代替模块设计文档；复杂规则继续放在对应 `module/` 或 `agent/` 目录。

