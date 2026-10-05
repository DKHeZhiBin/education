# 固定题目生成与 RAG 检索评估集

## 目标

本项目使用两套冻结评估集测量题目生产链路和教学检索链路。它们只用于离线评估，不参与母题选择、变式生成提示、生产检索、模型训练或自动准入。

| 评估集 | 规模 | 主要目标 |
| --- | ---: | --- |
| `question_generation_quadratic_v1` | 10 个生成案例 | 条件完整性、数学正确性、学段适配、答案泄露和可验证性 |
| `rag_retrieval_quadratic_v1` | 15 篇隔离语料、10 个查询 | 召回率、必选结果、禁止结果、重排和四级提示披露边界 |

两套 v1 数据均由项目为评估专门编写，范围限定为初中一元二次方程。它们不表示生产教材内容，也不应作为面向学生的引用来源。

## 题目生成评估集

每个案例包含母题、受控变式要求和独立 Oracle。Oracle 保存标准方程、实根集合、实根个数、必须满足的性质、禁止性质和确定性检查项。待测生成 Agent 只能看到 `input`，评估器才可以读取 `oracle` 与 `scoring`。

v1 覆盖：

- 两个整数根、重根和无实根；
- 非首一方程、分数根和异号根；
- 直接开平方法中的正负分支；
- 根与系数关系；
- 长方形情境中的正数定义域过滤。

确定性硬失败包括根集合错误、根个数错误、必要条件缺失、接受负边长和在题面泄露答案。语言质量分不能覆盖这些失败。

## RAG 检索评估集

RAG 评估语料拥有固定命名空间 `math_tutor_eval_rag_quadratic_v1`。语料包含概念、判别式、求解方法、例题模式、错误模式、四级提示和来源元数据。查询标注以下集合：

- `relevant_document_ids`：相关结果，用于 Recall@K 和重排指标；
- `required_document_ids`：K 个结果中必须出现的核心依据；
- `forbidden_document_ids`：不应返回的内容，主要阻止低级提示泄露完整题解；
- `minimum_recall_at_k` 与 `k`：每个查询的最低召回门槛。

建议汇总以下指标：

1. Recall@K：相关文档进入前 K 的比例；
2. Required Hit Rate：必选文档命中比例；
3. Forbidden Hit Rate：禁止文档进入前 K 的比例，目标为 0；
4. MRR 或 nDCG：核心依据在重排结果中的位置；
5. Hint Leakage Rate：一级至三级提示返回完整答案或完整题解的比例，目标为 0；
6. Source Accuracy：来源查询是否返回正确版本信息。

## 隔离规则

隔离由数据、加载器和生产 payload 三层共同保证：

1. 每条记录固定为 `evaluation_only=true`，manifest 固定为 `production_index_forbidden=true`；
2. manifest 保存数据文件 SHA-256、数量和有序 ID，任何原地修改都会使加载失败；
3. `app.evaluation.datasets` 拒绝 RAG 评估命名空间与 `QDRANT_COLLECTION` 相同；
4. 生产 `QdrantTeachingPayload` 只接受 `evaluation_only=false`；
5. 评估加载器只读取本地文件，不连接 MySQL、Redis 或 Qdrant，也不提供写入动作；
6. 若需要真实检索评估，评估运行器必须创建或清空同名评估集合，并使用独立 Qdrant collection；运行后可以整体删除该集合；
7. 生产索引同步器不得扫描 `evals/`，也不得接受这两个 manifest 作为摄取清单。

## 校验与运行边界

安装项目后可执行：

```bash
math-tutor-evals
```

该命令只校验 Pydantic 合约、文件哈希、数量、ID、查询引用和生产集合隔离，不建立索引，也不运行模型。可通过 `--production-collection` 指定准备对比的生产集合名。

真正的生成评估运行器应把每次输出与 Oracle 分离存储，并记录模型版本、提示版本、验证器版本、代码提交和数据 manifest 哈希。真正的 RAG 评估运行器应只将隔离 corpus 写入 manifest 指定的评估集合，并在报告中同时保存原始召回结果和重排结果。

## 版本策略

v1 文件冻结。修改题面、Oracle、评分权重、语料、相关性标注、禁止结果、K 值或阈值时，复制为新版本并生成新的 manifest 与 SHA-256。旧版本保留用于比较历史结果，不回写修正。
