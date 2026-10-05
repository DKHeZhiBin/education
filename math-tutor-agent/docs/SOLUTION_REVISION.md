# 解答校验失败后的有限修订流程

## 1. 目标

解题分析结果必须先通过 `SolutionVerificationAgent` 才能被教学 Agent 当作可靠解法使用。校验失败后，系统允许 `SolutionAnalysisAgent` 根据结构化失败证据进行有限次数修订，并对每个新版本重新执行完整校验。

默认最大修订次数为 `2`。修订次数不包含初次解题分析，因此一次新题运行最多包含：

```text
题目理解
→ 初始解题分析
→ 初始校验
→ 修订 1 → 校验 1
→ 修订 2 → 校验 2
→ 教学回复
```

最坏情况下共调用 8 个 Agent 步骤，与默认 `HARNESS_MAX_AGENT_CALLS=8` 对齐。

## 2. 可修订失败

以下问题可以退回解题分析 Agent：

- 候选方法答案冲突；
- SymPy 确认的错误答案、漏解或不等价步骤；
- 模型复核发现的条件遗漏、推理跳步或边界问题；
- 证明题的失败维度、硬性阻断项或仍需补足的论证；
- 解法结构缺少推荐方法、步骤或明确结论；
- 已有验证器给出了可以定位的问题或限制，并且模型 Provider 可用。

修订 Agent 接收 `ProblemSpec`、上一版 `SolutionPlan` 和对应 `VerificationReport`。它只能针对报告中的问题修改解法，不能改变题目条件、删除校验证据或用文字声明覆盖确定性工具失败。

## 3. 不进入重试的情况

以下情况立即停止，不消耗剩余修订次数：

- 校验已经通过；
- LLM Provider 未配置或不可用；
- 校验报告明确表示证明复核模型或普通模型不可用；
- 报告为 `unverified`，同时没有可用于修订的具体问题；
- `ProblemSpec` 仍存在阻断歧义，此时应先向用户澄清。

这些情况不能通过重复调用获得新的数学证据。

## 4. 最大次数与终止状态

配置项：

```dotenv
SOLUTION_MAX_REVISION_ATTEMPTS=2
```

允许范围为 `0..3`：

- `0`：关闭自动修订；
- `1`：最多修订一次；
- `2`：默认值；
- `3`：适用于明确增加了调用预算的环境。

Harness 需要预留：

```text
4 + 2 × SOLUTION_MAX_REVISION_ATTEMPTS
```

次 Agent 调用预算。如果 `HARNESS_MAX_AGENT_CALLS` 小于该值，配置校验会拒绝启动，避免流程运行到一半才发现预算不足。

每份 `VerificationReport 2.1` 包含：

```json
{
  "revision_context": {
    "attempt": 1,
    "max_attempts": 2,
    "will_retry": true,
    "exhausted": false,
    "termination_reason": "retryable_failure"
  }
}
```

`termination_reason` 取值：

| 值 | 含义 |
| --- | --- |
| `passed` | 当前版本通过，停止修订 |
| `retryable_failure` | 当前失败可修订，并且仍有次数 |
| `not_revisable` | 外部能力不可用或没有可执行的修订依据 |
| `limit_reached` | 当前版本仍失败，且已经达到最大修订次数 |

达到上限后，最后一份报告设置 `exhausted=true`、`will_retry=false`。教学 Agent 只能看到 `passed=false`，不得展示候选完整解法。

## 5. Artifact 与追踪

- 初始方案和每次修订都保存为新的 `solution_plan` artifact；
- 初始校验和每次重新校验都保存为新的 `verification_report` artifact；
- `SolutionPlan.revision_attempt` 从 `0` 开始，修订版依次为 `1..N`；
- `SolutionPlan.revision_reason` 保存本次修订所依据的问题摘要；
- 同一轮的 artifact 共用 `run_id`，MySQL 中按 step 顺序保存；
- Orchestrator 总是读取最后一个 `solution_plan` 和 `verification_report` 作为当前版本。

所有失败版本都保留，便于定位问题和后续评估，不会被新版本覆盖。

## 6. 安全边界

- SymPy 等确定性工具的失败结果不能被修订 Prompt 改写为通过；
- 每次修订后必须重新运行校验，不能继承上一版通过状态；
- 达到上限不自动降低通过门槛；
- 证明题仍受部分覆盖和单模型置信度上限约束；
- 自动修订只处理内部候选解法，不修改学生原始题目和作答记录。
