# 冻结评估数据

本目录包含三类互相独立的固定数据：高难数学解题评估、初中一元二次方程题目生成评估、以及使用独立语料的 RAG 检索评估。所有记录都标记为 `evaluation_only=true`，不得进入生产题库、生产 RAG、训练或微调数据。

## 当前版本

`data/high_difficulty_v1.jsonl` 包含 16 道高中竞赛难度题目：

| 源标签 | 数量 |
| --- | ---: |
| Algebra | 4 |
| NumberTheory | 3 |
| Geometry | 4 |
| Combinatorics | 5 |

每条记录保留原始英文题干、参考答案和参考解答，并包含来源提交、许可、人工审核依据和评估约束。`data/high_difficulty_v1.manifest.json` 保存选题 ID、分布和数据文件 SHA-256。

## 人工审核含义

这批题来自 MathOdyssey / GAIC Math 2024。上游说明写明：题目由高校和中学的专业数学命题者编写，命题委员会负责命题、审核、格式检查、测试和修订。因此本地记录使用：

```json
{"status":"source_committee_reviewed","local_content_unchanged":true}
```

这表示原题、答案和解答继承了来源委员会审核。它不表示本项目的人员已经做了第二轮签字审核。本项目另做了题面完整性筛查，剔除了变量未定义或英文表述有歧义的记录；排除项及原因保存在 manifest。若后续翻译、改写题目或修改参考解答，必须把 `local_content_unchanged` 改为 `false`，并在本地审核完成前把状态改成 `local_review_required`。

来源：

- MathOdyssey repository: https://github.com/protagolabs/odyssey-math
- 固定提交：`fe9e83df06111728e1b06ddaee0a60837c07d6c9`
- 数据论文：Fang et al., *MathOdyssey: Benchmarking Mathematical Problem-Solving Skills in Large Language Models Using Odyssey Math Data*, 2024.

## 使用限制

- 仅用于测试和评估；
- 不得用于训练或微调；
- 保留 MathOdyssey 署名和本目录的 `NOTICE.md`；
- 上游新贡献采用 CC BY-SA 4.0，并附加“允许作为商业测试集、禁止作为训练集”的条件；
- 题目与图片版权仍归原作者；本批没有选择需要外部图片的题目。

## 记录合约

每条 JSONL 包含：

- `source`：数据集、上游 ID、固定提交、许可和用途；
- `human_review`：审核组织、审核范围和证据链接；
- `taxonomy`：难度、语言和上游标签；
- `problem`、`reference_answer`、`reference_solution`：未经本地改写的源内容；
- `evaluation_contract`：必须产生的 Agent artifact 和最低评估要求。

Pydantic 合约位于 `app/domain/evaluation.py`。

## 重建

先从固定提交下载源 JSONL，再执行：

```bash
python3 evals/build_mathodyssey_subset.py \
  --source /path/to/final-odyssey-math-with-levels.jsonl
```

构建器只接受预设的 16 个上游 ID，并会拒绝缺少题干、答案、解答或高中竞赛等级的记录。

## 首轮评估维度

1. `ProblemSpec` 是否识别全部条件和目标；
2. `SolutionPlan` 是否给出至少一条完整路线和关键突破口；
3. 最终答案是否与参考答案数学等价；
4. `VerificationReport` 是否提供独立证据并正确表达覆盖范围；
5. 证明或组合论证不能把“未发现错误”写成形式化验证通过；
6. 教学回复是否遵守四级提示和完整答案门槛。

参考解答用于评估输出，不应直接放入待测 Agent 的输入上下文。

## 题目生成评估

- 数据：`data/question_generation_quadratic_v1.jsonl`
- 清单：`data/question_generation_quadratic_v1.manifest.json`
- 规模：10 个冻结案例
- 范围：初中一元二次方程

运行时只向生成 Agent 提供 `input`，`oracle` 和 `scoring` 只由评估器读取。

## RAG 检索评估

- 隔离语料：`data/rag_retrieval_quadratic_corpus_v1.jsonl`
- 查询与相关性标注：`data/rag_retrieval_quadratic_queries_v1.jsonl`
- 清单：`data/rag_retrieval_quadratic_v1.manifest.json`
- 评估命名空间：`math_tutor_eval_rag_quadratic_v1`

该命名空间不得等于生产 `QDRANT_COLLECTION`。评估语料不得混入生产 collection；需要真实检索实验时，应建立独立 collection，并在运行结束后按集合整体清理。

## 完整性校验

```bash
math-tutor-evals
```

校验器会检查文件 SHA-256、数量、有序 ID、Pydantic 合约、查询所引用的文档及评估命名空间隔离。它只读本地文件，不连接或修改 MySQL、Redis、Qdrant。

详细规则见 `docs/FIXED_EVALUATION_SUITES.md`。

## RAG 质量评分

把隔离检索运行结果保存为 JSONL 后执行：

```bash
math-tutor-rag-quality --results /path/to/rag-run.jsonl
```

输出包含宏平均 Recall@K、重排 nDCG@K、答案依据一致性和引用正确率。运行记录合约与评分口径见 `docs/RAG_QUALITY_METRICS.md`。
