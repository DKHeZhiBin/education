# 隔离上下文独立解题 Agent

## 1. 目标

`IndependentSolvingAgent` 从候选题本身重新求解，生成一份等待验证的结构化题解。它用于建立与变式生成过程相互独立的第二条解题路径，避免生成 Agent 同时出题、给答案并自行证明答案正确。

独立解题成功只证明系统获得了一份独立候选答案，不证明答案正确，也不允许批准题目。

## 2. 隔离通过数据投影实现

独立性由 `IndependentSolvingRepository.load_agent_context()` 的数据投影保证。传给模型的 `IndependentSolverContext` 只包含：

- 候选题 ID、内容哈希和状态版本；
- 题干与规范化表达；
- 学科、学段、题型、难度和答案类型；
- 显式条件、隐含条件和求解目标；
- 题目知识点。

以下内容不会出现在 Agent 上下文中：

- 生成 Agent 的输出对象、答案或推理；
- 生成提示和生成批次配置；
- 母题及母题题解；
- 数据库中已有的 `KnowledgeSolution`；
- 条件检查报告正文和其他准入证据；
- SymPy、数值验证或其他验证器结果。

Repository 会读取最新 `condition_completeness` 证据来决定是否允许开始解题，但只检查其状态和绑定的题目内容哈希，不把证据载荷传给 Agent。

## 3. 执行前提

候选题必须满足：

- 状态为 `candidate`、`validating` 或 `revision_required`；
- 具有生成批次；
- 具有学段、结构化目标和显式条件；
- 最新 `condition_completeness` 证据为 `passed`；
- 条件检查证据绑定的内容哈希与当前题目一致。

模型与提示版本必须启用。提示版本要求：

```text
purpose = independent_problem_solving
output_schema_version = 1.0
```

登记的模型名称必须与当前 LLM Provider 实际模型一致。

## 4. 解题输出

`IndependentSolutionDraft` 包含：

- 方法名称；
- 公开、可审计的完整解答文本；
- 最终答案或完整解集；
- 答案类型；
- 带稳定 ID、顺序、依赖和依据的结构化步骤；
- 关键突破口；
- 使用的假设；
- 模型置信度；
- 固定为 `true` 的 `requires_external_verification`。

Agent 只要求输出供审核和验证使用的公开步骤，不保存模型私有思维过程。

本地规则还会检查：

- 答案类型与题目目标一致；
- 步骤 ID 和序号唯一、连续；
- 步骤只能依赖更早步骤；
- 突破口只能引用存在的步骤；
- 解题使用的知识点不能超出题目范围；
- 置信度低于 0.2 的输出不写入题库。

## 5. 题解持久化

`IndependentSolvingRepository.persist_solution()` 把草稿写成 `KnowledgeSolution`：

```text
review_status = unreviewed
verification_status = unverified
is_preferred = false
verification_coverage.level = none
```

题解不会自动成为首选题解，不会携带“已验证”覆盖声明。元数据记录：

- 题目内容哈希；
- 隔离输入指纹；
- 模型与提示版本；
- 没有读取生成上下文、母题、已有题解或验证结果；
- 等待外部确定性验证。

同一题目和同一题解内容哈希重复写入时返回已有记录。已有记录如果已经被验证，或者隔离输入指纹不一致，不会被本流程冒充为新的独立未验证题解。

## 6. 独立性证据

保存题解后，Repository 写入阻断型证据：

```text
evidence_type = solution_independence
producer_type = system
status = passed
is_blocking = true
```

该证据由系统上下文白名单和输入指纹产生，因此使用 `producer_type=system`。实际解题模型和提示版本保存在证据载荷与题解元数据中。

证据明确记录 `correctness_verified=false`。后续准入流程仍然必须取得符号验证、数值验证和约束验证证据。

## 7. 并发与过期保护

模型调用前生成隔离输入指纹。写入时 Repository 会锁定题目并重新确认：

- 题目内容哈希未改变；
- 状态版本未改变；
- 生成批次和来源未改变；
- 条件完整性证据仍然有效；
- 模型与提示版本仍启用。

任何一项改变都会拒绝写入，要求基于最新题目重新独立求解。

## 8. 调用示例

```python
loaded = repository.load_agent_context(
    session,
    problem_id=problem_id,
    model_version_id=model_version_id,
    prompt_version_id=prompt_version_id,
)
draft = agent.run(
    context=loaded.solver_context,
    expected_model_name=loaded.model_name,
    versioned_prompt=loaded.versioned_prompt,
)
result = repository.persist_solution(
    session,
    context=loaded,
    draft=draft,
)
```

下一阶段由一元二次方程 SymPy 验证器读取这份 `unverified` 题解，独立校验方程、根数量、定义域、代回结果和边界条件。
