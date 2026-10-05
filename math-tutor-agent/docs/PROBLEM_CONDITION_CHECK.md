# 题意与条件检查 Agent

## 1. 职责

`ProblemConditionCheckAgent` 对 AI 生成的候选题执行第一轮质量检查，覆盖：

1. 题意歧义；
2. 条件完整性；
3. 定义域；
4. 解的数量语义与风险；
5. 学段适配。

Agent 不读取 `KnowledgeSolution`、母题答案或生成 Agent 的隐藏推理，不输出具体解、答案、步骤或证明。它只能写入阻断型 `condition_completeness` 准入证据，不能把题目改成 `approved` 或 `indexed`。

## 2. 输入边界

调用方使用 `ProblemConditionCheckRepository.load_agent_context()` 加载上下文。允许检查的状态为：

- `candidate`；
- `validating`；
- `revision_required`。

候选题必须具有 `generation_batch_id` 和 `mother_problem_id`。Repository 会重新确认母题仍然满足：

- `metadata_json.trusted_mother=true`；
- 状态为 `approved` 或 `indexed`。

传给 Agent 的内容只有候选题题干、条件、目标、题型、难度、答案类型、知识点，以及母题的学段、题型和知识点范围。

检查所用 `PromptVersion` 必须满足：

```text
purpose = problem_condition_check
output_schema_version = 1.0
active = true
```

`ModelVersion` 也必须启用，且登记的模型名称必须与当前 LLM Provider 实际配置一致。

## 3. 输出对象

`ProblemConditionCheckReport` 包含五个维度。每个维度都有：

- `status`：`passed`、`failed` 或 `inconclusive`；
- `confidence`：0–1；
- `summary`：检查摘要；
- `issues`：稳定问题编码、阻断级别、证据和建议修改方式。

总状态由系统计算：

```text
任一 failed       → failed
没有 failed，但有 inconclusive → inconclusive
五项全部 passed   → passed
```

`approval_eligible` 永远是 `false`。模型返回 `true` 会被拒绝。

## 4. 五项检查规则

### 4.1 题意歧义

检查目标缺失、符号未定义、指代不清、量词不明，以及同一题干存在多个合理解释。缺少结构化目标会被本地规则直接判为阻断问题。

### 4.2 条件完整性

检查显式条件和隐含条件是否足以支持目标，条件之间是否冲突，以及 `answer_type` 是否与 `target.expected_answer_type` 一致。

以下情况由本地规则直接失败：

- 没有显式条件；
- 缺少求解目标；
- 目标答案类型与题目答案类型冲突。

### 4.3 定义域

检查变量、参数和结果所在集合。系统会同时读取：

- `condition_type=domain` 的条件；
- 题干和目标限制中的实数、整数、正数、非负等定义域措辞。

两者都不存在时产生 `domain_missing` 阻断问题。

### 4.4 解的数量

这一维度检查“数量语义”，包括：

- 题目要求全部解、一个解、固定数量、至少或至多多少个解；
- 参数或条件是否可能令方程退化；
- 是否存在漏解、多解、增根或数量表述风险；
- 模型对根数量的非权威预测。

报告可以保存 `predicted_solution_count`，但不能保存具体根。无论预测置信度多高，`deterministic_verification_required` 都必须为 `true`。

本 Agent 的 `passed` 只表示题目的数量要求清楚、未发现结构冲突，不表示实际根数已经被证明。实际根数必须由后续隔离解题和 SymPy 验证器确认。`answer_type` 表示解集但题干未要求全部解时，本地规则直接失败。

### 4.5 学段适配

检查题型、知识点、表达方式、抽象程度和计算深度是否适合声明的学段。本地规则会阻止：

- 候选题学段与母题学段不一致；
- 候选题题型与母题题型不一致；
- 候选题引入母题之外的知识点。

## 5. 模型判断与本地规则合并

模型负责自然语言歧义、条件关系和教学适配判断，本地规则负责可确定的结构约束。

合并时：

1. 任一本地阻断问题都会把对应维度设为 `failed`；
2. 模型给出 `passed` 但置信度低于 0.5 时降为 `inconclusive`；
3. 模型不能删除本地发现的问题；
4. 模型输出答案、根、解题步骤或隐藏推理字段时整次检查失败；
5. 无法确认时保留 `inconclusive`，后续准入门会阻止批准。

## 6. 证据持久化

`ProblemConditionCheckRepository.persist_report()` 将报告保存为：

```text
evidence_type = condition_completeness
producer_type = model
is_blocking = true
status = report.overall_status
```

证据载荷包含题目内容哈希、状态版本、完整检查报告以及“解数量确定性验证待执行”标记。

写入前 Repository 会锁定题目，并检查：

- 内容哈希没有改变；
- `status_version` 没有改变；
- 生成批次没有改变；
- 题目仍处于准入前状态；
- 模型与提示版本仍处于启用状态。

完全相同的报告通过证据哈希幂等返回已有记录。证据写入不会改变题目状态。

## 7. 调用示例

```python
loaded = repository.load_agent_context(
    session,
    problem_id=problem_id,
    model_version_id=model_version_id,
    prompt_version_id=prompt_version_id,
)
report = agent.run(
    context=loaded.check_context,
    expected_model_name=loaded.model_name,
    versioned_prompt=loaded.versioned_prompt,
)
evidence = repository.persist_report(
    session,
    context=loaded,
    report=report,
)
```

Provider 不可用、输出 Schema 错误、夹带答案、版本不一致和题目并发修改都会产生稳定错误，不生成伪造的通过证据。
