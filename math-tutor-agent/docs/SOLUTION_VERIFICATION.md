# 解答校验 Agent

## 1. 校验顺序

`SolutionVerificationAgent` 采用确定性工具优先的校验链：

1. 检查 `SolutionPlan` 是否已经报告答案冲突；
2. 根据 `ProblemSpec.question_type` 判断 SymPy 是否适用；
3. 使用与 MCP Server 相同的安全数学工具独立求解和检查步骤；
4. SymPy 完全覆盖且全部通过时直接生成通过报告；
5. SymPy 只覆盖一部分或不支持该题型时，把结构化 CAS 报告交给模型复核；
6. 任一确定性检查失败时直接返回失败，模型不能覆盖该结论。

Harness 在进程内直接调用 `app.mcp_tools.math_tools`，避免为每次校验启动 MCP 传输；OpenClaw 和其他 Host 仍可通过 MCP Server 使用同一套工具及安全边界。

## 2. 当前 SymPy 覆盖范围

### 一元实方程

- 从 `ProblemSpec.known_conditions` 或规范题干提取单一方程；
- 使用 `solve_equation` 独立求出完整实数解集；
- 使用 `compare_math_steps` 比较推荐方法相邻方程的实数解集；
- 使用 `verify_candidate_answer` 把每种方法的候选值代回原方程；
- 比较候选答案是否覆盖独立求得的完整解集，防止二次方程漏解。

逐步等价检查聚焦推荐方法。其他候选方法会核对最终答案；其内部步骤尚未全部程序化验证时会写入 `limitations`。

### 算术与基础代数式

- 从规范题干提取安全表达式；
- 通过符号差化简检查原表达式与候选答案是否等价。

表达式仍受 AST 节点数、长度、指数、变量名和允许运算符白名单限制。

### 证明题专用复核

一般证明题不会进入普通的模型补充校验，而是进入六维证明复核：目标对应、条件使用、逻辑连续性、定理适用条件、分类完整性和结论闭合。单模型证明复核的覆盖范围固定为 `partial`，暂时通过的置信度封顶为 `0.74`。完整门槛、硬性阻断项和未验证主张规则见 `docs/PROOF_VERIFICATION.md`。

### 其他暂不自动覆盖

组合计算、概率建模、统计解释、方程组、含函数调用的表达式及超出安全解析器范围的高等数学，需要模型或后续专用验证器复核。无法覆盖不会被记录成数学错误，但在没有可用复核器时 `passed=false`。

## 3. VerificationReport 2.1

| 字段 | 含义 |
| --- | --- |
| `passed` | 当前证据是否足以允许教学 Agent 使用解法 |
| `verifier_type` | `cas`、`model`、`hybrid` 或 `unverified` |
| `coverage` | `full`、`partial` 或 `none` |
| `checks[]` | 每项工具检查及其状态、方法、步骤和证据 |
| `evidence` | 面向日志和调试的简短证据摘要 |
| `issues[]` | 已确认的问题 |
| `limitations[]` | 尚未覆盖的部分 |
| `confidence` | 对校验结论的置信度 |
| `proof_review` | 证明题六维审查、阻断问题、未验证主张和置信度上限；其他题型为 `null` |

单项检查状态：

- `passed`：工具确认该性质成立；
- `failed`：工具确认候选步骤、答案或解集不成立；
- `skipped`：输入超出该工具能力，需要其他验证器。
- `not_applicable`：证明题规则明确允许该维度不适用。

`skipped` 不等于通过。只要最终证据不足，教学 Agent 就不能展示完整解法。

校验结果写入题库时，需要投影为 `KnowledgeSolution.verification_coverage`：每项检查明确关联所覆盖的步骤，未覆盖步骤进入 `uncovered_step_ids`，工具限制进入 `limitations`。只有所有结构化步骤都被通过的检查覆盖时，题解才能标记为 `verified`；证明题等覆盖不完整的内容保持 `partial`。

## 4. 校验失败后的修订

校验失败不会直接放宽通过条件。具有具体错误证据且模型可用时，Orchestrator 将报告退回解题分析 Agent，默认最多修订两次；每个修订版本都必须重新执行本文件定义的完整校验。外部模型不可用、没有可执行修订依据或达到次数上限时立即停止。完整流程见 `docs/SOLUTION_REVISION.md`。

## 5. 安全边界

- 数学文本通过 Python AST 白名单构造 SymPy 对象，不使用 `eval` 或不受控的 `sympify`；
- 仅接受受限长度、节点数量、数字范围和指数范围的表达式；
- 确定性失败不能被模型改写为通过；
- 工具输出只保存规范表达式、残差和解集，不保存模型内部推理；
- `verification_report` artifact 使用 schema version `2.1`。
