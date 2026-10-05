# 隔离评估集泄漏检测

## 目标

`EvaluationLeakageDetector` 检查 AI 候选题是否复制、轻微改写或翻译了冻结评估题。检测结果写入阻断型 `evaluation_leakage_detection`，是自动批准的必需证据。

这个流程与生产题库重复检测分离：

- 评估题不写入 MySQL 知识表；
- 评估题不进入 RAG、向量索引或普通相似题池；
- 评估答案和参考题解不进入检测上下文；
- Evidence 不保存评估题原文或文本特征；
- 生产 Agent 不会收到评估题或参考答案。

## 冻结数据完整性

默认检查：

- `evals/data/high_difficulty_v1.manifest.json`；
- `evals/data/high_difficulty_v1.jsonl`。

加载器在计算相似度前验证：

1. manifest 和数据文件存在且可读取；
2. manifest Schema 为 `1.0`；
3. `evaluation_only=true`；
4. 数据文件 SHA-256 与 manifest 一致；
5. 实际题目数与 `case_count` 一致；
6. 题目 ID 与冻结 ID 清单一致；
7. 每条记录使用相同固定上游提交；
8. 每条记录的用途为 `evaluation_only`。

任一检查失败都返回 `inconclusive`。缺失或损坏的评估集不会被当作“没有泄漏”。

## 数据隔离

JSONL 每条记录解析后立即移除 `reference_answer` 和 `reference_solution`。检测上下文只保留：

- 评估 case ID；
- 固定来源提交和题型标签；
- 规范题干哈希；
- 字符四元组特征；
- 数学 Token 特征；
- 数值特征和公式复杂度。

报告与数据库 Evidence 只保存命中 case ID、来源版本和相似度。题目原文、答案、题解和特征集合均不持久化。

## 相似度维度

### 规范文本

执行 Unicode NFKC、大小写、空白、标点和常见 LaTeX 排版命令规范化：

- 规范哈希相同：`exact_text`；
- 字符四元组 Jaccard 不低于 `0.92`：`near_text`。

### 公式结构

从 `$...$`、`$$...$$`、`\(...\)`、`\[...\]` 和候选题结构化方程中提取数学 Token。变量按出现顺序重命名，保留数字、运算符及 `frac`、`sqrt`、`sum` 等有意义的 LaTeX 命令。

公式特征和数值特征同时高度相似，并且双方公式复杂度至少为 8 个 Token 时，标记为 `structural`。这条规则用于发现自然语言已翻译但公式与数字保持不变的泄漏。

### 联合分数

默认权重：

- 文本 `0.55`；
- 公式 `0.35`；
- 数值 `0.10`。

联合分数不低于 `0.90` 且文本相似度不低于 `0.80` 时标记为 `combined`。

## 状态规则

| 状态 | 条件 | 准入效果 |
|---|---|---|
| `passed` | 完整冻结集没有任何命中 | 满足评估集防泄漏门槛 |
| `failed` | 存在 `exact_text`、`near_text`、`structural` 或 `combined` 命中 | 阻止自动准入 |
| `inconclusive` | 数据缺失、哈希不符、版本不符或记录不完整 | 阻止自动准入 |

任何命中都不能由模型复核意见覆盖。后续流程应进入自动修订或隔离，并禁止写入生产索引。

## 并发与版本

加载时记录候选内容哈希、状态版本、评估集 SHA-256、case ID 集合哈希和全部题面特征。保存前重新读取候选题并重新校验冻结数据；候选题或评估集发生变化时拒绝写入旧结果。

验证器使用 `verifier_key=evaluation_leakage`。规则门槛、特征算法或冻结集版本变化时应登记新的 VerifierVersion。

## 调用顺序

```python
repository = EvaluationLeakageRepository()
loaded = repository.load_detector_context(
    session,
    problem_id=problem_id,
    verifier_version_id=verifier_version_id,
)

report = EvaluationLeakageDetector().detect(loaded.leakage_context)
evidence = repository.persist_report(session, context=loaded, report=report)
session.commit()
```

检测器只追加证据，不改变题目状态。生产索引仍只能接收状态机批准并且最新 `evaluation_leakage_detection=passed` 的内容。该证据必须由 `producer_type=verifier` 且带有 `verifier_version_id` 的正式检测器生成；导入脚本或普通系统任务写入的同名 `passed` 证据不能通过准入门。
