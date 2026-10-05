# Qdrant 向量存储接入

## 1. 选择结论

首版向量存储采用 Qdrant，使用一个版本化集合、一个名为 `dense` 的稠密向量和 Cosine 距离。

选择原因：

- 原生支持向量相似度与 payload 条件过滤；
- 可以为内容状态、题型、年级和知识点建立 payload 索引；
- Python 客户端同时支持本地 Qdrant 与 Qdrant Cloud；
- 不要求 Agent、Harness 或领域对象依赖 Qdrant 类型；
- 后续可以增加稀疏向量和混合查询，无需修改 `KnowledgeRetriever` 接口。

实现使用 Qdrant 当前统一查询接口 `query_points`。过滤字段创建 payload index，避免生产数据量上升后对 payload 全量扫描。参考 [Qdrant Quickstart](https://qdrant.tech/documentation/quickstart/)、[Collections](https://qdrant.tech/documentation/manage-data/collections/) 和 [Text filtering](https://qdrant.tech/documentation/search/text-search/text-filtering/)。

## 2. 运行结构

```text
KnowledgeQuery
      │
      ▼
EmbeddingProvider ── POST /embeddings
      │ query vector
      ▼
QdrantKnowledgeRetriever
      │ query_points + payload filter
      ▼
Qdrant collection: math_tutor_knowledge_v1
      │ structured teaching_object + citation
      ▼
RetrievedTeachingContext → AgentTeachingContext
```

Embedding 与向量库分开配置。当前提供 `OpenAICompatibleEmbeddingProvider`，兼容带 `/embeddings` 接口的服务。向量维度必须同时匹配 Embedding 返回值与 Qdrant 集合定义。

## 3. 集合定义

默认集合：

| 项目 | 默认值 |
| --- | --- |
| 集合 | `math_tutor_knowledge_v1` |
| 向量名 | `dense` |
| 距离 | `Cosine` |
| 维度 | `1024`，由 `EMBEDDING_DIMENSIONS` 指定 |

集合必须使用命名向量。管理工具发现已有集合时会核对向量名、维度和距离，不会自动重建或覆盖不兼容集合。

## 4. Payload 合约

每个 point 使用 `QdrantTeachingPayload`：

- `schema_version`、`index_version`
- `index_status=staging|active`；只有 `active` 可以被检索
- `content_status=approved|indexed`
- `entity_type`、`entity_id`
- 学科、年级、知识点、题型、内容类型和教材版本
- 难度与难度来源
- `disclosure_level`，提示对象额外保存 `hint_level`
- `evaluation_only=false`
- 用于生成向量的 `search_text`
- 不含 score 和引用的 `teaching_object`
- `citation`
- 来源内容哈希与 Embedding 模型名

写入前领域对象会再次验证 `teaching_object`。评估集无法通过该 Payload Schema；候选、修订中、隔离或退役内容也无法写成活动 point。

检索时固定过滤：

1. `index_status=active`；
2. `content_status` 为 `approved` 或 `indexed`；
3. `evaluation_only=false`，隔离评估集；
4. Embedding 模型与当前配置一致；
5. `entity_type` 符合当前查询用途；
6. 学科、语言以及请求中的年级、知识点、题型和教材版本过滤；
7. 提示教学额外限制 `disclosure_level <= hint_level`。

返回 payload 仍需通过 `RetrievedConcept`、`RetrievedPrinciple`、`RetrievedHint` 等领域 Schema，格式错误或越级内容直接丢弃。

## 5. Payload 索引

集合创建时为以下字段建立索引：

- 状态与版本：`schema_version`、`index_status`、`content_status`、`evaluation_only`、`index_version`
- 内容身份：`entity_type`、`entity_id`
- 教学范围：`subject`、`grade_band`、`grade_codes`、`language`
- 知识结构：`knowledge_point_codes`、`problem_types`、`content_types`
- 难度：`difficulty`、`difficulty_sources`
- 教材：`curriculum_version`、`curriculum_version_id`
- 提示披露：`disclosure_level`、`hint_level`
- 向量来源：`embedding_model`

## 6. 配置

```dotenv
RAG_ENABLED=true
RAG_PROVIDER=hybrid
RAG_TOP_K=5
RAG_TIMEOUT_SECONDS=3
RAG_MAX_CONTEXT_CHARS=12000
RAG_REQUIRED_FOR_READINESS=false

QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=math_tutor_knowledge_v1
QDRANT_VECTOR_NAME=dense
QDRANT_SCORE_THRESHOLD=0.25
QDRANT_OVERSAMPLING_FACTOR=4

EMBEDDING_BASE_URL=https://example-embedding-provider/v1
EMBEDDING_API_KEY=
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1024
EMBEDDING_TIMEOUT_SECONDS=15
EMBEDDING_READINESS_PATH=/models
```

本地 Qdrant 可以使用官方镜像：

```bash
docker run --name math-tutor-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v math-tutor-qdrant-data:/qdrant/storage \
  qdrant/qdrant
```

项目不会自动启动容器，也不会在 API 启动时修改集合结构。

## 7. 集合管理

安装项目依赖并完成配置后：

```bash
math-tutor-vector-store status
math-tutor-vector-store ensure-collection
```

`ensure-collection` 的职责只有：

1. 不存在时创建集合；
2. 已存在时校验命名向量、维度和距离；
3. 创建或确认 payload indexes，包括生成批次、验证覆盖级别和验证器版本 ID。

该集合管理命令不会导入 MySQL 内容。批准内容由 `math-tutor-index sync` 构建成 `VectorPoint` 并同步到 Qdrant。

## 8. 就绪与故障

Qdrant Provider 的就绪检查依次确认：

1. Embedding Provider 配置完整且轻量探针可访问；
2. Qdrant 可连接；
3. 集合存在；
4. 命名向量、维度和 Cosine 距离匹配。

单次 Embedding 或 Qdrant 查询失败时，Retriever 返回 `status=degraded` 和短错误类别，不返回原始异常、URL、密钥或响应正文。是否阻止实例接流量由 `RAG_REQUIRED_FOR_READINESS` 决定。

## 9. 当前边界

本次完成 Qdrant 客户端、集合管理、Embedding Provider、结构化向量 Payload、向量检索、元数据过滤、Provider 注册和就绪检查接入。

MySQL 关键词生产索引和 `approved` 内容同步由 `math-tutor-index` 提供。`HybridKnowledgeRetriever` 使用加权 RRF 合并 MySQL 关键词候选与 Qdrant 向量候选，并按题目条件、求解目标和解法结构重排。题目退役、重新验证和版本更新通过持久化维护任务删除或重建 Qdrant Point。
