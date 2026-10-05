# MySQL 关键词索引与 Qdrant 生产同步

## 1. 目标

生产索引只接收已经通过准入的内容：

- 题目必须为 `content_status=approved`；
- 文档必须为 `review_status=approved` 且 `lifecycle_status=active`；
- 题解必须已审核，并达到 `partial` 或 `verified`；
- 提示必须为 `active=true`、`review_status=approved`；
- 文档切片必须为 `enabled=true`；
- 评估集无法通过 `QdrantTeachingPayload`，也不会被投影器读取。

候选、验证中、待修订、隔离和退役内容不会进入生产检索。

## 2. 统一投影

`knowledge_search_documents` 是 MySQL 关键词索引和 Qdrant 向量索引之间的规范投影。每行对应一个稳定的教学实体：

- `problem_pattern`
- `solution_outline`
- `error_pattern`
- `hint`
- `source_fact`

它保存稳定 point ID、来源内容哈希、Embedding 模型、索引版本、生成批次、验证覆盖、验证器版本、结构化 payload、标签和规范化 `search_text`。同一实体使用 `(entity_type, entity_id)` 唯一约束，重复同步只更新原记录。

题目相关 payload 使用 Schema `1.1`，新增以下可追溯信息：

- `generation_batch_id`：内容所属生成批次；
- `verification_level` 与 `verification_coverage`：完整覆盖级别、已覆盖步骤、未覆盖步骤、校验项、限制和置信度；
- `verifier_version_ids`：用于 Qdrant 元数据过滤的扁平版本 ID；
- `verifier_versions`：验证器键、版本号、实现哈希和规则集哈希。

题解、错误模式和提示携带其关联题解的验证覆盖。题目模式没有唯一对应题解，因此覆盖字段为空，但会携带该题目的验证器版本集合。教材文档切片不是生成题目，三类字段均为空。

`search_text` 使用 MySQL InnoDB `FULLTEXT` 索引，并指定内置 `ngram` parser，以支持中文关键词召回。只有 `index_status=active` 的记录允许被关键词查询。

## 3. 两阶段发布

每个题目或文档独立执行：

1. 从 MySQL 重新读取并锁定待同步的 `approved` 内容；
2. 构建并验证结构化教学对象；
3. 将统一投影写成 `staging`；
4. 对统一的 `search_text` 批量生成 Embedding；
5. 向 Qdrant 写入 `index_status=staging` 的不可检索 point；
6. 使用相同 point ID 将 Qdrant payload 激活；
7. 激活 MySQL 关键词记录；
8. 保存 `index_sync` 准入证据；
9. 将题目从 `approved` 转为 `indexed`，或将文档 `ingestion_status` 标为 `indexed`。

检索端始终过滤 `index_status=active`。在 Embedding 或 Qdrant 写入失败时，题目保持 `approved`，投影记录失败类型并允许重新执行。错误记录不保存密钥、URL、响应正文或原始异常。

## 4. 数据库升级

```bash
alembic upgrade 20261004_0017
```

`0015` 创建 `knowledge_search_documents`、普通过滤索引和 `ngram` 全文索引；`0016` 增加生成批次与验证溯源字段；`0017` 增加持久化索引维护任务。迁移不导入内容，也不连接 Qdrant。

## 5. 配置

```dotenv
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=math_tutor_knowledge_v1
QDRANT_VECTOR_NAME=dense

EMBEDDING_BASE_URL=https://your-provider.example/v1
EMBEDDING_API_KEY=
EMBEDDING_MODEL=your-embedding-model
EMBEDDING_DIMENSIONS=1024

PRODUCTION_INDEX_VERSION=v1
PRODUCTION_INDEX_SYNC_LIMIT=100
PRODUCTION_EMBEDDING_BATCH_SIZE=32
PRODUCTION_INDEX_TIMEOUT_SECONDS=30
```

`EMBEDDING_DIMENSIONS` 必须同时匹配 Embedding 返回维度和 Qdrant 集合维度。Embedding 模型变化时应提升 `PRODUCTION_INDEX_VERSION` 并重建索引，不能把不同模型生成的向量混在同一命名向量中。

## 6. 管理命令

查看等待同步和已同步数量：

```bash
math-tutor-index status
```

同步一批内容：

```bash
math-tutor-index sync
math-tutor-index sync --limit 25
```

命令返回处理的题目数、文档数、投影数和失败 owner ID。失败项保持可重试；命令不会批准内容，也不会把失败内容强制转为 `indexed`。

## 7. 关键词查询边界

`ProductionIndexRepository.keyword_search()` 使用 MySQL FULLTEXT 分数排序，并固定限制 `index_status=active`。查询应用与向量检索一致的学科、语言、学段、知识点、题型、内容类型、难度来源、教材版本和提示披露过滤。返回结果携带经过领域 Schema 验证的结构化 Qdrant payload，由 `HybridKnowledgeRetriever` 与向量候选执行加权 RRF 合并。

关键词和向量候选已经完成去重、排名融合，以及基于题目条件、求解目标和解法结构的教学重排。题目退役、重新验证和版本更新使用持久化维护任务删除或重建索引，详见 [INDEX_LIFECYCLE.md](./INDEX_LIFECYCLE.md)。
