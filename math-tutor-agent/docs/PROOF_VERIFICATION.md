# 非程序化证明题的验证规则

## 1. 目标与结论边界

本规则适用于当前不能由 SymPy、数值工具或形式化证明器完整判定的数学证明题。系统输出的是**结构化证明审查结果**，用于判断候选证明能否暂时进入教学流程。

以下表述具有不同含义：

- `passed=true`：在当前六项审查中证据齐全，未发现阻断问题，可暂时用于生成教学提示；
- `passed=false`：发现明确错误，或现有证据不足；
- `coverage=partial`：单模型审查只覆盖可读文本中的论证结构；
- “形式化证明完成”或“人工审核通过”：必须由后续形式化证明器或合格审核者提供独立证据。

单模型审查无论结果如何都不能生成 `coverage=full`，也不能将“没有发现错误”描述为“已经证明正确”。

题库自动准入时，只有 `partial` 覆盖的证明题会进入 `quarantined`，不能进入 `approved` 或生产索引。只有形式化证明器或带审核身份和时间的合格人工完整复核可以解除限制，详见 [证明题与开放题验证覆盖限制](./VERIFICATION_SCOPE_POLICY.md)。

## 2. 前置可审查条件

进入证明内容复核前，输入必须同时具备：

1. `ProblemSpec.question_type=proof`，或目标动作/答案类型明确为证明；
2. `target.action=prove` 且 `target.object` 明确；
3. `SolutionPlan` 能找到 `recommended_method_id` 对应的方法；
4. 推荐方法至少包含一个结构化步骤；
5. 推荐方法包含明确的最终结论。

任一条件缺失时：

- `passed=false`；
- `coverage=none`；
- `verifier_type=unverified`；
- 问题写入 `issues[]`，不调用证明内容复核。

## 3. 六项覆盖维度

| 维度 | 必查内容 | 允许 `not_applicable` | 典型失败 |
| --- | --- | --- | --- |
| `claim_alignment` | 实际证明的命题与题目目标完全一致 | 否 | 证明了逆命题、弱命题或另一结论 |
| `condition_usage` | 必要条件被正确使用，没有加入更强假设 | 否 | 默认图形特殊、偷偷假设非零或单调 |
| `logical_continuity` | 相邻论断有依据，关键链路连续且不循环 | 否 | “显然”掩盖关键跳步、用结论证明结论 |
| `theorem_applicability` | 定理、公式、引理的适用前提成立 | 是，仅在确实未使用时 | 未满足连续性、可导性、共线等前提 |
| `case_completeness` | 分类、边界、退化情形及必要方向完整 | 是，仅在题目确实无需分类时 | 漏掉零值、端点、反向或某一构型 |
| `conclusion_closure` | 最终一步明确推出原证明目标 | 否 | 推导停在中间结论，没有闭合到目标 |

每一项必须包含可定位到题目条件、证明步骤或结论的 `evidence`，且维度置信度至少为 `0.75`。没有证据、低于门槛或缺失的维度都会由系统改成 `unverified`。

## 4. 硬性阻断与未验证主张

出现以下任一项时必须拒绝：

- 证明目标错位；
- 使用未声明的关键假设；
- 循环论证；
- 关键定理前提不成立；
- 遗漏必要分类或方向；
- 关键结论只有断言，没有依据；
- 存在反例、内部矛盾或与已知条件冲突。

这些问题写入 `proof_review.hard_blockers[]`，同时进入 `issues[]`。

模型无法核验的外部引理、图形事实、计算结果或关键主张写入 `proof_review.unverified_claims[]`。列表非空时 `passed=false`，因为系统无法确认论证链的关键依赖。

## 5. 暂时通过规则

只有以下条件同时满足时，证明题才可暂时通过：

1. 六项维度全部返回且具有证据；
2. 每项维度置信度至少为 `0.75`；
3. 四项必需维度均为 `passed`；
4. `theorem_applicability` 和 `case_completeness` 为 `passed`，或符合限定条件的 `not_applicable`；
5. 没有 `failed` 或 `unverified` 维度；
6. `hard_blockers[]` 为空；
7. `unverified_claims[]` 为空；
8. 模型明确返回 `passed=true`；
9. 模型整体原始置信度至少为 `0.80`。

通过结果仍固定为：

```json
{
  "passed": true,
  "verifier_type": "model",
  "coverage": "partial",
  "confidence": 0.74
}
```

其中 `0.74` 是上限，实际值取模型原始置信度和该上限的较小值。

## 6. 置信度规则

`confidence` 表示系统对“本次接受或拒绝决定”的把握，不表示命题为真的概率，也不表示证明已经获得形式化认证。

| 场景 | `passed` | 最终置信度 |
| --- | --- | --- |
| 六项完整、无阻断、原始置信度 ≥ 0.80 | `true` | `min(raw_confidence, 0.74)` |
| 存在明确失败维度或硬性阻断 | `false` | `min(max(raw_confidence, 0.75), 0.95)` |
| 缺维度、证据不足、存在未验证主张或原始置信度不足 | `false` | 不高于 `0.49` |
| 证明复核模型不可用 | `false` | `0.20` |
| 输入结构缺失，无法进入内容复核 | `false` | `0.92`，表示对“当前不可审查”结论的把握 |

拒绝结果可以具有高置信度，因为系统可能非常确定候选证明存在逻辑错误。客户端展示时应同时读取 `passed`、`coverage`、`issues` 和 `limitations`，不能只显示置信度数字。

## 7. VerificationReport 2.1

证明题在通用报告上增加 `proof_review`：

```json
{
  "proof_review": {
    "criteria": [
      {
        "criterion": "logical_continuity",
        "status": "passed",
        "evidence": "第 2 步由第 1 步和所列定理推出",
        "confidence": 0.86
      }
    ],
    "hard_blockers": [],
    "unverified_claims": [],
    "raw_confidence": 0.86,
    "confidence_cap": 0.74
  }
}
```

单项状态包括：

- `passed`：该维度有支持证据；
- `failed`：发现具体逻辑错误；
- `not_applicable`：只允许用于规则明确许可的两个维度；
- `unverified`：缺少证据或当前能力无法检查。

通用 `checks[]` 会把 `unverified` 映射为 `skipped`，其余状态保持不变，以兼容已有校验日志。

## 8. 后续提升路径

如果需要把覆盖提升到 `full`，应按题型接入独立验证能力，例如 Lean、Isabelle 或 Coq 形式化证明、几何专用证明器、可复现计算证书，或者带审核身份与时间记录的人工复核。新增验证器必须保存输入映射、工具版本、验证结果和可追溯证据，不能仅增加另一次同模型调用。
