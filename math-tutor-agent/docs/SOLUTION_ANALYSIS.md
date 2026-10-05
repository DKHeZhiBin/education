# 解题分析 Agent

## 1. 职责

`SolutionAnalysisAgent` 接收已经确认的 `ProblemSpec`，生成供校验和教学使用的 `SolutionPlan 2.1`。它负责提出可靠的解法候选、比较方法、选择推荐路线并提取适合引导学生的关键突破口。

该 Agent 不直接面向学生输出完整推理。学生最终看到的内容仍由 `HintTeachingAgent` 根据校验结果、提示等级和本轮作答决定。

## 2. 多解法规则

只有整体策略、数学工具或关键构造明显不同时，才记录为不同解法。例如代数消元与几何构造可以作为两个方法；仅调整同一组代数步骤的顺序通常不应算作新方法。

- 最多保留 4 个可靠方法；
- 每个方法最多保留 20 个可检查步骤；
- 每一步包含操作、简短数学依据和本步结果；
- 每个方法记录适用条件、优点、局限、答案和置信度；
- 只有一种可靠方法时只返回一个，不强制生成替代方法。

`recommended_method_id` 根据学生学段、解释清晰度、步骤负担和可校验性选择。`recommendation_reason` 说明选择依据，不能只写“更简单”。

## 3. 关键突破口

`key_breakthroughs[]` 将解题中真正决定路线的结构单独提取出来：

| 字段 | 含义 |
| --- | --- |
| `title` | 关键点的短名称 |
| `description` | 需要识别的关系、结构或构造 |
| `why_it_matters` | 该发现如何推进求解 |
| `hint_question` | 不直接泄露答案的引导问题 |
| `related_method_ids[]` | 使用该突破口的方法 |

教学 Agent 优先从突破口生成最低必要提示，避免直接把完整步骤列表交给学生。

## 4. SolutionPlan 2.1

核心字段：

- `methods[]`：结构化解法候选；
- `recommended_method_id`、`recommendation_reason`：推荐路线；
- `answer_consistency`：`consistent`、`unconfirmed` 或 `conflict`；
- `key_breakthroughs[]`：教学突破口；
- `verification_targets[]`：校验 Agent 必须覆盖的等价变换、边界条件和结论；
- `assumptions[]`：原题允许但没有显式写出的常规约定；
- `knowledge_points[]`、`common_misconceptions[]`、`difficulty` 和 `confidence`；
- `steps[]`、`answer`：从推荐方法投影得到的兼容字段。
- `revision_attempt`：初始版本为 0，自动修订版依次递增；
- `revision_reason`：本次修订所依据的校验问题摘要。

如果不同方法的答案文本不一致，系统把 `answer_consistency` 标记为 `conflict`，将整体置信度限制在 0.4，并要求校验 Agent 明确复核。任何冲突都不能直接进入教学输出。

## 5. 降级行为

- `ProblemSpec` 仍有阻断歧义：返回空计划并要求先澄清；
- LLM 未配置且本地规则没有覆盖该题：返回空方法列表，不伪造解法；
- 模型只返回旧版 `steps`：自动包装成单一方法，保持旧 Provider 的兼容性；
- 模型没有提供突破口：从推荐方法第一步生成一个保守的起点问题。

`SolutionPlan` 默认只作为内部 artifact 保存。只有独立校验通过并满足教学策略时，学生端才会得到逐级提示或完整讲解。

当校验通过的方案进入题库时，推荐方法映射为 `KnowledgeSolution`：方法步骤写入 `steps`，步骤依据写入 `justifications`，关键突破口写入 `key_breakthroughs`。题库对象使用稳定步骤 ID，供验证覆盖、提示策略和后续修订引用；不能只保存一段完整题解文本。

校验失败后的定向修订、终止条件和最大次数见 `docs/SOLUTION_REVISION.md`。
