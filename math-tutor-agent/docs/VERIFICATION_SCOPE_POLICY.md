# 证明题与开放题验证覆盖限制

## 1. 状态含义

`partial` 是 `KnowledgeSolution.verification_status`，表示题解只有部分验证覆盖。`quarantined` 是 `KnowledgeProblem.content_status`，表示该题目版本不能批准或进入生产索引。

第一版采用以下映射：

| 现有证据 | 题解状态 | 题目状态 |
| --- | --- | --- |
| 模型结构审查通过，但没有权威完整覆盖 | `partial` | `quarantined` |
| 只有部分工具检查通过 | `partial` | `quarantined` |
| 没有可复核覆盖或存在失败 | `unverified` / `failed` | `quarantined` |
| 具备允许的权威完整覆盖，且其他准入规则全部通过 | `verified` | 可以继续自动准入 |

题目状态不新增 `partial`，避免把题解覆盖程度和内容生产状态混为一谈。

## 2. 受限题型识别

系统按结构化字段识别受限内容。

证明题满足任一条件：

- `problem_type` 是 `proof`、`geometric_proof` 或 `proof_problem`；
- `target.action=prove`；
- 题目或目标的答案类型为 `proof`。

开放题满足任一条件：

- `problem_type` 明确标记为开放、探究、调查或讨论；
- 答案类型为说明、论证、构造、多答案或开放回答；
- `target.action` 为 `construct` 或 `explain`；
- `metadata_json.open_ended=true`。

证明题优先按证明题规则分类。

## 3. 自动覆盖上限

普通 LLM 复核、同一模型再次复核以及“未发现错误”的文字结论，都不能把证明题或开放题提升为 `full/verified`。

自动准入门读取受限题型时会：

1. 检查当前题解和全部新鲜准入证据；
2. 缺少权威完整覆盖时，把错误的 `verified/full` 声明降为最高 `partial`；
3. 在题解覆盖限制中写明原因；
4. 写入带题型范围和覆盖状态的 `admission_decision`；
5. 直接将题目转为 `quarantined`，不消耗自动修订次数。

这类覆盖缺口来自验证能力边界，改写题干或题解不能产生新的确定性证据，因此不进入候选题自动修订流程。

## 4. 允许解除限制的证据

证明题只有以下任一新鲜证据可以形成权威完整覆盖：

- `formal_proof_verification`：由带版本号的形式化证明 Verifier 产生；
- `qualified_human_review`：由系统记录合格人工审核身份和时间。

开放题只有以下任一新鲜证据可以形成权威完整覆盖：

- `exhaustive_rubric_verification`：由带版本号的穷尽式评分规则 Verifier 产生；
- `qualified_human_review`：由系统记录合格人工审核身份和时间。

上述证据必须同时：

- 状态为 `passed`；
- 绑定当前题目与题解内容哈希；
- 声明 `coverage_level=full`；
- Verifier 证据带 `verifier_version_id`；
- 人工证据带 `reviewer_kind=qualified_human`、`reviewer_id` 和 `reviewed_at`。

模型生产的同名证据不被接受。

## 5. 双层保护

限制同时存在于两个入口：

- `RuleBasedAdmissionGate`：自动识别覆盖不足并选择 `quarantined`；
- `ProblemContentStateMachine`：任何直接请求 `approved` 的管理操作，如果缺少权威完整覆盖，会返回 `verification_coverage_insufficient`，建议状态为 `quarantined`。

因此调用方不能绕开自动准入门直接批准受限内容。

## 6. 通用解答校验

`SolutionVerificationAgent` 对证明题继续执行六维结构审查，并固定输出 `coverage=partial`。开放题走独立的模型结构复核分支，同样固定为 `partial`，置信度上限为 `0.74`。这些结果可以用于候选教学提示和内部审查，不能作为生产题库标准答案依据。
