# RAG 知识检索设计

## 1. 目标与当前范围

RAG 为题目理解、解法分析和分级教学提供可追溯的教材定义、定理、例题结构和教学依据。它是可选能力：关闭或暂未配置时，现有数学推理、SymPy 校验和分级提示链路继续运行。

当前已经建立稳定的 `KnowledgeRetriever` Provider 边界、可复现的文档摄取流程，并接入 Qdrant 与 MySQL FULLTEXT 混合检索。默认仍关闭 RAG，也不在每轮教学中自动发起检索。

## 2. 模块边界

```text
TeachingOrchestrator
        │  KnowledgeQuery
        ▼
KnowledgeRetriever Protocol
        ├── DisabledKnowledgeRetriever（当前默认）
        ├── QdrantKnowledgeRetriever（已接入）
        ├── HybridKnowledgeRetriever（已接入）
        └── Test/InMemory Retriever（按需）
        │  RetrievedTeachingContext
        ▼
Specialist Agent
```

核心文件：

- `app/domain/knowledge.py`：与后端无关的查询、引用和检索结果对象；
- `docs/RAG_DATA_MODEL.md`：来源、教材版本、文档、切片、题目和题解的数据关系；
- `docs/RAG_SOURCES.md`：首批允许来源、许可履约、题解准入和禁止清单；
- `app/providers/knowledge.py`：Provider 协议、关闭实现、注册表和工厂；
- `app/providers/qdrant_knowledge.py`：Qdrant 向量检索、过滤和结构化结果还原；
- `app/providers/hybrid_knowledge.py`：MySQL 关键词召回、Qdrant 向量召回和加权 RRF 融合；
- `app/retrieval/teaching_context.py`：两种 Provider 共用的过滤防线、去重、预算和结构化上下文组装；
- `app/providers/embeddings.py`：可替换的 OpenAI-compatible Embedding Provider；
- `app/vector_store/qdrant.py`：集合、payload indexes 和 point 写入边界；
- `app/harness/factory.py`：把检索器注入 `TeachingOrchestrator`；
- `app/core/config.py`：RAG 开关及通用参数。

Agent 和 Harness 不导入向量数据库客户端。具体适配器负责把公共查询翻译成后端查询，并把结果还原成统一的 `RetrievedTeachingContext`。

## 3. Provider 接口

`KnowledgeRetriever` 使用同步协议，与当前同步 Harness 一致：

```python
class KnowledgeRetriever(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def available(self) -> bool: ...

    def retrieve(self, query: KnowledgeQuery) -> RetrievedTeachingContext: ...
    def check_readiness(self) -> tuple[bool, str]: ...
    def close(self) -> None: ...
```

职责约束：

- `retrieve` 只检索和整理上下文，不生成最终答案；
- 每个片段必须携带 `KnowledgeCitation`，不能返回无来源正文；
- Provider 负责超时、后端错误映射和结果数量上限；
- Provider 不读写会话、用户和学习记录；
- `close` 释放连接池或客户端资源；
- 后续若 Harness 全面异步化，可以增加异步协议版本，但不能改变领域结果结构。

## 4. 查询与返回对象

### KnowledgeQuery

| 字段 | 含义 |
| --- | --- |
| `text` | 经过最小化处理的检索文本，最大 4000 字符 |
| `purpose` | `problem_understanding`、`solution_analysis`、`hint_teaching` 或 `source_lookup` |
| `filters` | 学科、年级、知识点、题型、难度、内容类型、教材版本和语言 |
| `top_k` | 返回上限，范围 1–20 |
| `hint_level` | 仅提示教学使用，必填且范围为 1–4 |
| `problem_structure` | 可选的题目条件、求解目标、解法方法和步骤结构，用于候选重排 |

`purpose` 用于限制不同阶段可看到的材料。例如一级提示阶段只应检索定义或方向性材料，不应直接检索完整题解。

### RetrievedTeachingContext

`RetrievedTeachingContext` 已改为结构化教学对象，不再向 Agent 暴露扁平的 `items[].content`：

| 内容组 | 含义 |
| --- | --- |
| `concepts` | 概念定义摘要、记号和先修知识 |
| `principles` | 定理、公式及适用条件 |
| `problem_patterns` | 条件、目标、题型结构和难度来源 |
| `solution_outlines` | 已验证的结构化解法轮廓 |
| `error_patterns` | 可观察错误信号和修复目标 |
| `hints` | 已批准并符合当前等级的提示蓝图 |
| `source_facts` | 只用于来源查询的短事实 |

原始 `RetrievedKnowledge` 只在 Provider 内部使用，单条候选也限制为 2000 字符。进入 Agent 前必须调用 `to_agent_context()`，该方法会移除查询、Provider 诊断和全部原始候选字段。

查询用途决定允许返回的内容组；提示教学还必须提供 `hint_level`，并校验每项 `disclosure_level`。一级至三级不能接收完整解法轮廓，第四级解法中的最终答案必须具有完整验证覆盖。详细字段、数量和字符预算见 [RETRIEVED_TEACHING_CONTEXT.md](./RETRIEVED_TEACHING_CONTEXT.md)。

## 5. 可关闭策略

默认配置：

```dotenv
RAG_ENABLED=false
RAG_PROVIDER=
RAG_TOP_K=5
RAG_TIMEOUT_SECONDS=3
RAG_MAX_CONTEXT_CHARS=12000
RAG_REQUIRED_FOR_READINESS=false
RAG_HYBRID_RRF_K=60
RAG_HYBRID_VECTOR_WEIGHT=1.0
RAG_HYBRID_KEYWORD_WEIGHT=1.0
RAG_RERANK_FUSION_WEIGHT=0.55
RAG_RERANK_CONDITION_WEIGHT=0.20
RAG_RERANK_TARGET_WEIGHT=0.15
RAG_RERANK_SOLUTION_WEIGHT=0.10
RAG_CACHE_ENABLED=true
RAG_CACHE_TTL_SECONDS=900
RAG_CACHE_NO_RESULTS_TTL_SECONDS=60
RAG_CACHE_SCHEMA_VERSION=v1
```

`RAG_ENABLED=false` 时，工厂返回 `DisabledKnowledgeRetriever`：

- 不创建网络客户端；
- 不访问向量库或嵌入模型；
- 如果被调用，返回 `status=disabled` 和空片段；
- 就绪检查显示 `disabled_by_configuration`；
- 教学编排器继续使用原有推理与验证路径。

如果设置 `RAG_ENABLED=true`，必须提供已经注册的 `RAG_PROVIDER`。未注册时应用在启动装配阶段直接报错，避免配置声称启用 RAG、运行时却悄悄不检索。

## 6. 可替换策略

具体适配器通过工厂加载；`qdrant` 与 `hybrid` 是内置 Provider，其他适配器仍可注册：

```python
register_knowledge_retriever("qdrant", build_qdrant_retriever)
```

适配器工厂接收统一 `Settings` 并返回满足协议的对象。切换后端只修改 Provider 注册与环境配置，不修改 Agent、Harness、API DTO 或领域对象。

`HybridKnowledgeRetriever` 使用两类排名来源：Qdrant 提供语义相似度排名，MySQL ngram FULLTEXT 提供关键词排名。两路使用相同的用途和元数据限制，以 `(entity_type, entity_id)` 去重，再通过加权 Reciprocal Rank Fusion 合并。RRF 只使用各路名次，避免直接相加量纲不同的余弦分数和全文相关度分数。任一路失败时，另一条链路仍可返回结构化结果，并将状态标为 `degraded`。

启用方式：

```dotenv
RAG_ENABLED=true
RAG_PROVIDER=hybrid
```

RRF 融合后由 `StructuralCandidateReranker` 执行确定性教学结构重排：

1. 比较查询条件与候选 `condition_schema` 或规范检索文本；
2. 比较求解目标与候选 `target_schema`；
3. 比较已知方法、关键突破口和步骤动作；
4. 将结构分数与 RRF 分数按配置权重重新归一化；
5. 缺少某类结构证据时移除该项权重，不以零分惩罚候选。

默认权重为融合排名 `0.55`、题目条件 `0.20`、求解目标 `0.15`、解法结构 `0.10`。查询没有显式结构时，条件和目标使用原题文本做保守比较，解法结构不做推断。最终进入 Agent 的仍然只有经过数量、字符预算和提示披露校验的 `RetrievedTeachingContext`。

Qdrant 仍只是候选存储，并非领域接口的一部分。完整配置与运维边界见 [QDRANT_VECTOR_STORE.md](./QDRANT_VECTOR_STORE.md) 和 [PRODUCTION_INDEXING.md](./PRODUCTION_INDEXING.md)。

## 7. 编排接入规则

`TeachingOrchestrator` 已接入确定性的 `OnDemandRetrievalPolicy`。决策过程不额外调用 LLM，每次把是否检索、用途、原因码和说明写入 `retrieval_decision` artifact。检索触发规则如下：

1. 题目存在教材定义、定理版本或符号解释需求时，为题目理解检索；
2. 解法分析缺少可追溯定理依据或需要同构例题时，为解法分析检索；
3. 提示教学只获取当前提示等级允许的内容；
4. 简单计算、已有可靠解法或检索价值低时跳过；
5. 检索失败、超时或没有结果时回到原教学链路，并在内部 trace 记录限制。

同一编排运行最多访问一次 RAG。题目理解阶段已经检索时，解法分析阶段会以 `run_retrieval_budget_used` 跳过；普通学生作答、完成确认、简单且高置信度的直接求解都会跳过。Provider 关闭时记录 `retriever_unavailable`，不会调用 `retrieve()`。

检索输出只有在存在经过结构校验的选中内容时才转换成 `AgentTeachingContext`。Provider 抛出异常时，Orchestrator 只记录异常类型和降级状态，不保存连接信息或响应正文，并继续原有题意理解、解题、验证和提示流程。

进入 Agent 上下文的结构化对象会提取为 `TutorReply.sources`，向用户保留标题、版本、URL、章节定位以及依据类型。来源按文档切片去重；没有进入 Agent 上下文的召回候选不会出现在用户响应中。前端在本轮回答下方展示“本轮参考依据”，版本缺失时明确标记，不推断或伪造版本。

成功和无结果的 `RetrievedTeachingContext` 会进入 Redis。缓存键由 Provider、缓存 Schema、MySQL 知识索引 generation 与规范化查询哈希组成；降级结果和异常不缓存。索引发布、退役、重新验证和版本替换会在 MySQL 状态事务内推进 generation，旧缓存随后不可达并按 TTL 回收。Redis 故障时直接调用原 Provider。

完整题解不得进入一级至三级提示上下文。学生历史数据与教材知识库使用不同检索接口和权限边界，不能混合索引。

## 8. 安全与数据治理

- 只索引拥有合法使用权且来源可追溯的教材、课程标准和题解；
- 高难题评估集标记为 `evaluation_only`，禁止写入 RAG；
- 不把学生姓名、联系方式、原始聊天历史或家长信息写入知识索引；
- 检索正文视为不可信输入，进入 Agent 前限制长度、类型和引用字段；
- 面向学生展示的外部结论保留来源与版本；
- 防止检索内容中的指令改变系统提示、工具权限或输出规则。

### 8.1 AI 生成题库的索引门槛

生成题目与 RAG 索引是两个独立流程。生成完成不代表允许检索，向量化完成也不代表内容已经通过准入。

AI 题目先进入 MySQL 候选区，依次经过条件完整性检查、隔离上下文独立解题、SymPy/数值/规则验证、结构化去重和独立 AI 复核。只有状态为 `approved` 的题目及题解能够进入生产索引；`candidate`、`validating`、`revision_required` 和 `quarantined` 内容必须由索引查询层过滤。

学生反馈内容错误或 Harness 检测到明确答案冲突时，系统立即隐藏 MySQL 检索投影、推进 Redis 缓存 generation，并创建 Qdrant 删除与重建任务。删除完成后题目进入新的 `validating` 轮次，旧轮次的数学与教学证据不能用于再次准入。完整流程见 [题目错误反馈与自动重新验证](./CONTENT_ISSUE_REVALIDATION.md)。

首版自动准入只覆盖可以被确定性程序完整验证的题型。证明题或开放题只有模型互审而缺少完整验证时，不得作为权威答案进入生产 RAG。每个索引项需要携带内容状态、验证覆盖、验证器版本、生成批次和来源 ID，以便撤回、重新验证和重建索引。

## 9. 就绪与故障策略

关闭时 RAG 不影响 `/v1/health/ready`。启用后，就绪检查调用当前 Provider 的 `check_readiness`。

- `RAG_REQUIRED_FOR_READINESS=false`：Provider 故障会显示降级，但实例仍可服务原教学链路；
- `RAG_REQUIRED_FOR_READINESS=true`：Provider 故障会使实例未就绪，适用于业务已经强依赖知识库的部署；
- 单次检索失败应返回 `degraded` 或受控异常，由编排器回退，不能伪造来源或返回缓存外的猜测内容。

## 10. 后续实施顺序

1. 建立知识点目录、可信母题、题目状态和生成批次的数据结构；
2. 建立文档导入、清洗、切片、去重和版本管理流程；（已完成）
3. 实现变式生成、条件检查、独立解题、数学验证、去重和复核流水线；
4. 先开放可被程序完整验证的代数与数值题自动准入；
5. 为内容补充年级、知识点、题型、难度来源、教材版本和内容类型标签；
6. 建立题目、结构化解法步骤、可观察错误模式和四级提示蓝图的关联；（已完成）
7. 定义有界、分用途、分提示等级的结构化教学上下文；（已完成）
8. 建立 MySQL ngram 关键词生产索引；（已完成）
9. 建立混合召回、状态过滤、重排与引用组装；
10. 在 Orchestrator 中加入按需检索决策和分级上下文裁剪；（已完成）
11. 增加 Redis 检索缓存及知识库版本失效；
12. 使用隔离评估集验证生成正确率、准入误放率、召回率、重排质量和引用正确性。
