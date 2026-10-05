# 候选题有限自动修订

## 1. 目标

候选题只有在规则化准入门给出 `revision_required`，并留下明确失败证据后，才允许调用修订 Agent。每条候选题版本链最多修订两次；第二次修订后的版本再次失败时，准入门直接将其隔离。

修订只生成新的 `candidate` 版本，不能批准内容，也不能复用旧版本的通过证据。

## 2. 触发条件

`CandidateRevisionRepository` 只接受同时满足以下条件的题目：

- 具有生成批次、生成 Job、可信母题关系；
- 当前状态为 `revision_required`；
- 最新 `admission_decision` 为 `failed/revise`，目标状态为 `revision_required`；
- 决策绑定当前题目内容哈希和转换前的状态版本；
- 决策列出了至少一个失败类型；
- 修订次数没有超过系统配置、Job 预算和硬上限 2 中的最小值。

重复检测、评估集泄漏和来源权利失败属于不可自动修订风险，仍由准入门直接隔离。

## 3. Agent 可见上下文

Repository 构造 `CandidateRevisionContext`，只向模型提供：

- 当前题干、显式和隐含条件、求解目标；
- 受保护的学科、年级、题型、答案类型、语言、知识点、变式类型和母题 ID；
- 原生成 Job 的难度范围和禁用词；
- 最新准入决策中引用的明确失败证据；
- 上下文指纹、当前修订次数和最大次数。

证据载荷经过白名单投影，只保留公开检查结果、阻断问题、覆盖范围和修订建议。模型输出必须让 `repairs` 中的证据 ID 与输入失败证据 ID 完全相等。

## 4. 修订边界

修订 Agent 必须遵守以下规则：

1. 只处理输入中列出的失败，不自行扩大任务；
2. 不改变题型、答案类型、知识点集合、变式类型和母题；
3. 不引入新知识，难度不能超出原 Job 范围；
4. 不通过删除必要条件来规避校验；
5. 不输出答案、解法、证明、根集合、隐藏推理或批准结论；
6. 修订后题干或结构必须发生实质变化；
7. `requires_full_revalidation` 固定为 `true`。

Agent 层与 Repository 层各执行一次输出约束检查，防止调用方绕过 Agent 后直接写入不合规结果。

## 5. 版本与幂等

修订不会原地覆盖旧题。Repository 创建新的 `knowledge_problems` 行：

```text
失败版本（revision_required）
  └── 新版本（candidate）
        └── 重新执行全部检查
```

新版本保留相同生成批次、可信母题和来源引用，并通过元数据记录：

- `revision_root_problem_id`；
- `revised_from_problem_id`；
- `revision_attempt`；
- `revision_context_fingerprint`；
- `admission_decision_id`；
- `failure_evidence_ids`；
- 模型版本和提示版本。

版本身份为 `candidate-revision:{root_problem_id}:{attempt}`。相同输入重放会返回已创建版本；身份相同但内容或来源链不同会报版本冲突。旧题元数据记录 `superseded_by_problem_id`，旧状态和证据保持不变。

## 6. 重新验证与证据

新版本只写入一条非阻断的 `revision_generation` 审计证据，记录失败证据、逐条修复、内容哈希、模型和提示版本。旧题的条件检查、独立题解、符号验证、数值验证、重复检测、泄漏检测和 AI 复核结果都不会复制到新版本。

后续执行顺序重新从头开始：

1. `candidate → validating`；
2. 题意与条件检查；
3. 隔离上下文独立解题；
4. SymPy、数值、定义域和边界检查；
5. 四层重复检测和评估集泄漏检查；
6. 独立 AI 复核；
7. 规则化自动准入。

## 7. 两次上限

```text
原始候选失败 → 第 1 次修订候选
第 1 次修订候选失败 → 第 2 次修订候选
第 2 次修订候选失败 → quarantined
```

`KNOWLEDGE_PROBLEM_MAX_REVISION_ATTEMPTS` 允许配置为 1 或 2，Job 的 `max_revision_rounds` 允许配置为 0 到 2。实际可用次数取配置、Job 预算和硬上限 2 的最小值，任何模型意见都不能提高该上限。

## 8. 事务调用

调用方先在只读阶段加载受约束上下文并运行 Agent，再在事务中持久化：

```python
agent_context = repository.load_agent_context(
    session,
    problem_id=problem_id,
    model_version_id=model_version_id,
    prompt_version_id=prompt_version_id,
)
draft = agent.run(
    context=agent_context.revision_context,
    expected_model_name=agent_context.model_name,
    versioned_prompt=agent_context.versioned_prompt,
)

with session.begin():
    result = repository.persist_revision(
        session,
        agent_context=agent_context,
        draft=draft,
    )
```

持久化时会锁定失败版本并重新构造上下文。题目、准入决策或失败证据发生变化时拒绝写入，调用方需要重新加载后再决定是否修订。
