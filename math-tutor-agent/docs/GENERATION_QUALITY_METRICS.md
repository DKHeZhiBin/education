# 题库生成质量指标

## 目标

质量报告从 MySQL 中已有的候选题、准入证据和自动决策实时计算，不创建一份容易失真的汇总副本。报告支持按生成批次、批次用途、知识点和生成时间范围筛选。默认只统计 `question_variation`，防止可信母题导入和重新验证批次混入 AI 变式生成质量。

所有指标只读取绑定当前 `problem_content_hash` 的最新证据。题目修订前的条件检查、验证和准入结论仍保留在审计记录中，但不进入当前内容的指标。

## 五项指标

| 指标 | 分子 | 分母 | 缺失处理 |
| --- | --- | --- | --- |
| 题意有效率 | 最新 `condition_completeness=passed` | 条件检查已有 `passed` 或 `failed` 结论的生成题 | `not_run`、`inconclusive`、缺失计入 `unavailable_count` |
| 答案正确率 | 同一选定题解的符号、数值、约束验证全部通过 | 同一题解的三类验证均已有明确结论的生成题 | 任一类缺失或不确定时不进入分母 |
| 确定性验证覆盖率 | 已完成符号、数值、约束、重复、评估泄漏五类检查 | 范围内全部生成题 | 未完成的题计入 `unavailable_count` |
| 重复拦截率 | 重复检测失败后自动决策为 `revise` 或 `quarantine` | 最新重复检测为 `failed` 的生成题 | 没有确认重复时返回 `no_samples`，不显示虚假的 0% |
| 自动准入率 | 最终自动决策为 `approve` | 最终决策为 `approve`、`revise` 或 `quarantine` 的生成题 | `wait` 和没有决策的题计入 `unavailable_count` |
| 错误内容自动准入率 | 批准时证据不满足门槛，或批准后同一内容出现阻断失败证据 | 当前内容版本曾被自动 `approve` 的生成题 | 用户报告本身不算确认错误，必须形成阻断失败证据 |

所有比率同时返回 `rate`（0 至 1）和 `percentage`（0 至 100）。分母为 0 时两者均为 `null`，状态为 `no_samples`。

## 答案证据一致性

答案正确率不能把不同题解的验证结果拼在一起。报告优先读取最新自动准入决策中的 `selected_solution_id`，然后只聚合同一题解、同一内容哈希下的：

- `symbolic_verification`；
- `numeric_verification`；
- `constraint_verification`。

还没有准入决策时，报告选择最近产生答案验证证据的题解。该选择只用于质量观察，不会批准内容。

## 查询方式

管理员接口：

```http
GET /v1/admin/generation/quality-report
GET /v1/admin/generation/quality-report?batch_id=<uuid>
GET /v1/admin/generation/quality-report?topic_code=MS.QE
GET /v1/admin/generation/quality-report?batch_purpose=question_variation
GET /v1/admin/generation/quality-report?created_from=2026-10-01T00:00:00Z&created_to=2026-11-01T00:00:00Z
```

命令行：

```bash
math-tutor-quality-report --topic-code MS.QE
math-tutor-quality-report --batch-id <uuid>
```

接口需要管理员身份。命令行直接读取配置中的 MySQL，输出相同的 JSON 合约。

## 上线阻断门

默认配置：

```dotenv
QUALITY_MAX_ERRONEOUS_ADMISSION_RATE=0
QUALITY_RELEASE_MIN_AUTO_ADMISSIONS=1
```

执行：

```bash
math-tutor-release-gate --topic-code MS.QE
```

以下任一条件成立时返回 `status=blocked`，并以退出码 `2` 结束，发布流水线必须停止：

1. 自动准入样本少于 `QUALITY_RELEASE_MIN_AUTO_ADMISSIONS`；
2. 错误内容自动准入率高于 `QUALITY_MAX_ERRONEOUS_ADMISSION_RATE`。

默认阈值为 0%，所以任何一条确认的错误准入都会阻断上线。报告中的 `erroneous_admissions` 保留题目、批次、批准证据、失败证据和稳定原因编码，用于定位问题。管理员也可以读取：

```http
GET /v1/admin/generation/release-gate
```

## 解读边界

- 题意有效率反映条件检查 Agent 的明确结论，不等同于人工标注准确率；后续应使用固定生成评估集校准。
- 答案正确率要求两类独立数学证据和约束检查都完成，不能只依据模型复核意见。
- 重复拦截率衡量规则门是否阻止已经检测出的重复题，不表示候选题本身的重复发生率。
- 自动准入率高不必然表示质量高，必须同时关注错误内容被准入的比例；该指标仍是上线阻断项。
