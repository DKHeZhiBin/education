# RAG 检索与回答质量指标

## 目标

本评估使用冻结的 `rag_retrieval_quadratic_v1` 查询和隔离语料，分别测量检索、重排、答案依据和引用。评估结果不能从生产索引取样，也不能把评估语料写入生产 Qdrant collection。

每次运行保存一条 JSONL 记录，包含初始召回顺序、重排顺序、回答主张、主张依据和引用。评估器只根据固定相关性标注及结构化证据计算指标。

## 指标口径

### 检索召回率

每条查询计算：

```text
Recall@K = 前 K 个重排结果中的相关文档数 / 该查询的相关文档总数
```

总分是所有已运行查询 Recall@K 的宏平均。报告同时记录：

- 必选文档是否全部命中；
- 禁止文档进入前 K 的次数；
- 是否达到查询自己的 `minimum_recall_at_k`。

### 重排质量

重排质量使用 nDCG@K：

- `required_document_ids` 相关度为 2；
- 其他 `relevant_document_ids` 相关度为 1；
- 无关、禁止或未知文档相关度为 0。

报告同时计算初始召回 nDCG、重排后 nDCG 和两者差值。重排器不能引入初始召回中不存在的文档。

### 答案依据一致性

回答拆成独立主张，每条主张必须由确定性程序、隔离 Judge 或人工标为 `supported`、`unsupported` 或 `not_assessed`。隔离 Judge 的版本必须写入 `evidence_judge_version`。

一条主张只有同时满足以下条件才算一致：

1. 独立评估结果为 `supported`；
2. 至少提供一个依据文档；
3. 所有依据都存在于冻结语料并进入该查询前 K；
4. 至少一个依据属于相关文档；
5. 没有使用禁止文档。

指标为一致主张数除以已评估主张数。`not_assessed` 不进入分母；完全没有已评估主张时返回 `no_samples`。

### 引用正确性

一条引用必须同时满足：

1. 引用绑定到存在且已被判定为依据一致的主张；
2. 引用文档进入前 K，且属于该查询相关文档；
3. 引用文档确实列在该主张的依据中；
4. 引用的 `source_version` 与冻结语料元数据完全一致。

正确引用数除以全部引用数得到引用正确率。没有引用时返回 `no_samples`。

## 运行记录格式

每行对应一个评估查询：

```json
{
  "schema_version": "1.0",
  "run_id": "rag-eval-20261006-001",
  "query_id": "rag_query_002",
  "evaluation_only": true,
  "index_namespace": "math_tutor_eval_rag_quadratic_v1",
  "initial_document_ids": [
    "rag_qe_concept_standard_form",
    "rag_qe_principle_discriminant"
  ],
  "reranked_document_ids": [
    "rag_qe_principle_discriminant",
    "rag_qe_concept_standard_form"
  ],
  "answer_claims": [
    {
      "claim_id": "claim-1",
      "text": "判别式为 Δ=b²-4ac。",
      "evidence_document_ids": ["rag_qe_principle_discriminant"],
      "support_status": "supported",
      "assessment_method": "isolated_judge"
    }
  ],
  "citations": [
    {
      "claim_id": "claim-1",
      "document_id": "rag_qe_principle_discriminant",
      "source_version": "eval-authored-v1"
    }
  ],
  "retriever_version": "hybrid-v1",
  "reranker_version": "structural-v1",
  "answer_model_version": "provider-model-snapshot",
  "evidence_judge_version": "isolated-grounding-judge-v1"
}
```

初始检索无结果时，两个文档 ID 数组可以为空，这会产生 0 分召回和 nDCG。`reranked_document_ids` 必须是 `initial_document_ids` 的子集。

## 运行命令

```bash
math-tutor-rag-quality --results /path/to/rag-run.jsonl
```

评估器会先验证冻结语料 SHA-256、查询 ID、独立命名空间及生产 collection 隔离，再输出四项聚合指标与逐查询结果。

当前命令只评价已经保存的运行结果，不主动调用生产检索器或回答模型。这样可以固定运行输入、保留原始排序，并在模型或索引版本变化后重复比较。
