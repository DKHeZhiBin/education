# 独立 AI 复核 Agent

## 1. 目标

`IndependentReviewAgent` 是候选题自动准入前的模型裁判。它比较：

1. 候选题解给出的最终答案；
2. SymPy 与数值验证器重新计算的独立答案；
3. 符号、数值和约束三类确定性工具证据；
4. 年级、知识点、难度、答案类型和解法结构五类教学标签。

输出写成阻断型 `pedagogical_review` 证据。Agent 不能改变题目状态、执行索引或覆盖工具结论。

## 2. “候选答案”和“独立答案”的含义

变式生成 Agent 按既有隔离规则只生成题目，不生成答案。因此本流程中：

- **候选答案**：隔离解题 Agent 写入 `KnowledgeSolution.final_answer` 的待审答案；
- **独立答案**：SymPy `computed_roots` 和 Decimal 数值验证器 `independently_computed_roots` 从题目重新计算出的结果。

这避免让出题模型同时生成答案并自行审核，也不需要破坏现有的生成隔离设计。

## 3. 输入条件

Repository 只接受：

- 具有生成批次且状态为 `candidate`、`validating` 或 `revision_required` 的题目；
- 来源为 `independent_solving_agent` 的结构化候选题解；
- 与当前题目和题解内容哈希绑定的最新 `solution_independence` 证据；
- 与当前内容哈希绑定、带 `verifier_version_id` 的最新 `symbolic_verification`、`numeric_verification` 和 `constraint_verification` 证据；
- 完整的学段、求解目标和知识点标签。

模型版本和提示版本必须启用。提示版本要求：

```text
purpose = independent_pedagogical_review
output_schema_version = 1.0
```

登记的模型名必须与实际 LLM Provider 一致。

## 4. 结构化输出

`IndependentReviewReport` 包含：

- `answer_comparison`：候选答案与全部独立答案的一致性；
- `tool_assessments`：三条工具证据的身份、原状态和复核说明；
- `teaching_assessments`：五个固定教学维度；
- `blocking_issues`：导致失败的明确问题；
- `revision_instructions`：只针对公开错误的修订要求；
- `strengths` 与 `confidence`；
- `passed`、`failed` 或 `inconclusive` 决策。

模型必须原样回填 problem、solution、上下文指纹、候选答案、独立答案、证据 ID 和证据状态。任何替换、遗漏或伪造都会被拒绝。

## 5. 确定性证据优先

Agent 层和 Repository 层分别执行同样的底线规则：

- 任一工具证据为 `failed`，复核只能为 `failed`；
- 任一工具证据为 `not_run` 或 `inconclusive`，复核不能为 `passed`；
- `passed` 要求答案比较、三项工具评估及五项教学评估全部为 `aligned`；
- `passed` 的置信度不得低于 `0.8`；
- 答案冲突、定义域冲突或答案不完整必须成为阻断问题；
- 模型意见不能覆盖 SymPy、数值、约束或后续泄漏检测失败。

模型输出即使通过 Pydantic Schema，也必须继续通过 Repository 的上下文绑定和确定性上限检查。

## 6. 教学标签检查

| 维度 | 检查内容 |
|---|---|
| `grade_band` | 题面、方法和计算复杂度是否适合标注学段 |
| `knowledge_points` | 实际步骤是否只使用并覆盖声明的知识点 |
| `difficulty` | 难度值和难度来源是否与所需推理量一致 |
| `answer_type` | 求解目标、候选答案形式和标签是否一致 |
| `solution_structure` | 步骤是否有序、有依据，关键突破口是否与步骤对应 |

教学标签复核是内容质量门槛，不代表真实学生能力标签，也不会写入 `LearnerState`。

## 7. 持久化和状态

复核结果写入：

```text
evidence_type = pedagogical_review
producer_type = model
is_blocking = true
model_version_id = 当前模型版本
prompt_version_id = 当前提示版本
```

题解自身的 `review_status` 同步为：

- `passed → approved`；
- `failed → rejected`；
- `inconclusive → pending`。

这只表示题解经过该轮独立 AI 复核。题目仍须满足其余全部准入证据，才能从 `validating` 进入 `approved`。

## 8. 并发和审计

模型调用前，输入生成完整上下文指纹。写入时 Repository 锁定题目和题解，重新读取最新工具证据并重建指纹。题目、题解、状态版本、工具结果或标签发生变化时，旧报告拒绝写入。

Evidence 保存候选答案、独立答案、复核明细、来源证据 ID、模型版本和提示版本。模型私有推理不保存。

## 9. 调用方式

```python
loaded = repository.load_agent_context(
    session,
    problem_id=problem_id,
    solution_id=solution_id,
    model_version_id=model_version_id,
    prompt_version_id=prompt_version_id,
)
report = agent.run(
    context=loaded.review_context,
    expected_model_name=loaded.model_name,
    versioned_prompt=loaded.versioned_prompt,
)
evidence = repository.persist_report(
    session,
    context=loaded,
    report=report,
)
session.commit()
```
