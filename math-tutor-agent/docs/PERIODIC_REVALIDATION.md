# 已批准题目的定期交叉复核与批量重验

## 1. 目标

生产题库中的题目不会因为曾经通过一次审核就永久可信。模型、提示词、验证器、教材标签和准入规则都会变化，因此系统需要周期性地重新检查 `approved` 与 `indexed` 内容。

本流程完成两类复核：

1. **隔离 AI 交叉复核**：重新检查题意与条件，由独立解题 Agent 生成新题解，再由复核 Agent 比较题目、新题解、工具证据和教学标签。
2. **确定性工具重验**：重新执行 SymPy、独立数值验证、四层重复检测和评估集泄漏检测。

AI 结论不能覆盖确定性失败。任何工具失败、证据缺失或执行异常都会使题目保持在生产检索之外。

## 2. 数据对象

迁移 `20261006_0020` 增加三张表：

- `content_revalidation_policies`：复核范围、周期、批量上限，以及固定的模型、提示词和验证器版本。
- `content_revalidation_runs`：每次定时或人工执行的批次、计数和总结。
- `content_revalidation_items`：逐题状态、内容哈希、条件检查证据、独立解题证据、工具证据、AI 复核证据、准入证据和失败原因。

策略可以按学科、知识点和题型限定范围。同一道题存在未结束复核项时不会被新批次再次选中。每题还记录上次周期复核时间，因此系统会按策略周期轮转处理，而不是始终选择同一批题。

## 3. 执行流程

```text
选择到期策略
  -> 选择 approved / indexed 题目并冻结内容哈希
  -> 停用关键词索引并删除 Qdrant 向量
  -> 题目进入 validating
  -> AI 题意与条件检查
  -> 隔离 AI 独立解题
  -> SymPy 验证
  -> 数值抽样或穷举验证
  -> 文本 / 公式 AST / 条件 / 解法四层查重
  -> 隔离评估集泄漏检查
  -> 独立 AI 教学复核
  -> 规则化准入门
  -> 通过后重建关键词与 Qdrant 索引
```

开始复核时先执行索引停用。这样即使模型、MySQL、Qdrant 或进程在中途失败，待复核题目也不会继续作为生产标准答案被检索。

准入通过后，已有索引生命周期任务会等待题目回到 `approved`，随后重建 MySQL 关键词索引和 Qdrant 向量索引，并触发知识库缓存版本失效。失败或结论不充分的题目不会重建索引。

## 4. 状态与恢复

批次状态：

- `pending`：已创建，尚未处理。
- `running`：正在逐题处理。
- `completed`：全部题目通过，或批次没有到期题目。
- `partial_failed`：部分通过，部分失败或结论不充分。
- `failed`：全部题目失败。
- `cancelled`：保留给管理操作。

逐题状态：

```text
queued -> suppressing -> validating -> tool_verification
       -> ai_review -> admission -> passed | failed | inconclusive
```

运行同一个批次时，终态题目会被跳过，未完成题目从已保存状态继续执行。每次工具和 AI 产出的证据都写入原有准入审计表，复核项只保存证据 ID，避免复制证据正文。

## 5. 配置策略

先升级数据库：

```bash
alembic upgrade head
```

准备策略 JSON。所有版本 ID 必须已经登记且处于启用状态；提示词用途和验证器类型会在保存策略时校验。

```json
{
  "policy_key": "monthly-ms-quadratic",
  "enabled": true,
  "cadence_hours": 720,
  "max_items_per_run": 50,
  "subject": "math",
  "topic_code": "MS.QE",
  "problem_type": "equation_solving",
  "execution_model_version_id": "<model-version-id>",
  "review_model_version_id": "<review-model-version-id>",
  "condition_prompt_version_id": "<condition-prompt-id>",
  "solver_prompt_version_id": "<solver-prompt-id>",
  "review_prompt_version_id": "<review-prompt-id>",
  "sympy_verifier_version_id": "<sympy-verifier-id>",
  "numeric_verifier_version_id": "<numeric-verifier-id>",
  "duplicate_verifier_version_id": "<duplicate-verifier-id>",
  "leakage_verifier_version_id": "<leakage-verifier-id>",
  "next_run_at": "2026-10-07T00:00:00Z",
  "config": {}
}
```

```bash
math-tutor-revalidate configure --file revalidation-policy.json
math-tutor-revalidate run-due
```

人工强制执行一个指定策略：

```bash
math-tutor-revalidate run-due --policy-key monthly-ms-quadratic --force
```

查看或恢复已有批次：

```bash
math-tutor-revalidate status <run-id>
math-tutor-revalidate process <run-id>
```

## 6. 定时触发

应用内部保存“何时到期”和幂等批次记录，外部调度器只需要周期调用一次：

```bash
math-tutor-revalidate run-due
```

生产环境可使用 Kubernetes CronJob、云调度任务或系统服务计时器每小时调用。策略自身的 `next_run_at` 决定是否真正创建批次，所以提高外部唤醒频率不会缩短复核周期。

避免让多个调度实例长期并发执行同一命令。策略读取使用数据库行锁，同一题目的活动复核项也会在候选查询中排除；部署时仍建议由单个定时 Worker 负责创建和处理批次。

## 7. 管理 API

以下接口只允许管理员访问：

- `PUT /v1/admin/revalidation/policies/{policy_key}`：创建或更新策略。
- `POST /v1/admin/revalidation/runs/run-due`：执行到期策略；请求体支持指定策略和强制执行。
- `POST /v1/admin/revalidation/runs/{run_id}/process`：恢复未完成批次。
- `GET /v1/admin/revalidation/runs/{run_id}`：查看批次和逐题证据。

长批次建议通过 CLI Worker 执行，HTTP 接口更适合小批量人工操作和管理后台联调。

## 8. 故障与安全边界

- 内容哈希在入队后发生变化：该题失败，不使用旧快照继续审核，并尝试按当前版本立即停用生产索引。
- 题目已不再是 `approved/indexed`：跳过生产复核并记录失败原因。
- Qdrant 删除失败：索引维护任务保留为可重试失败，题目不会进入后续准入。
- 任一确定性验证失败：准入门只能修订、隔离或等待，AI 无权批准。
- AI 输出无效或 Provider 不可用：记录失败，题目留在生产索引之外。
- 重新批准成功但索引重建失败：索引任务可重试；题目在索引恢复前不会被当作已完成复核内容返回。

批次统计的 `passed` 表示完整证据链通过并触发索引恢复；`failed` 与 `inconclusive` 都不能用于生产教学检索。
