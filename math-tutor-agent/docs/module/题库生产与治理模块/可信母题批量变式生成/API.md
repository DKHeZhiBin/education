# 可信母题批量变式生成 HTTP API

## 1. 文档目的

本文集中说明可信母题批量变式生成的 HTTP 接口。业务目标和完整流程见[可信母题批量变式生成](./README.md)，任务输入、输出、预算和幂等规则见 [QuestionGenerationJob 合约](./QUESTION_GENERATION_JOB.md)，暂停、恢复、取消和重试规则见[生成批次管理](./GENERATION_BATCH_MANAGEMENT.md)。

## 2. 身份与权限

所有接口都使用 `/v1/admin/generation` 前缀，并要求管理员 Bearer Token。普通学生和家长账号不能创建、执行、查询或管理生成批次。

## 3. 接口列表

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/v1/admin/generation/jobs` | 幂等登记并执行批次 |
| `POST` | `/v1/admin/generation/jobs/{job_id}/run` | 执行或恢复已有 Job |
| `GET` | `/v1/admin/generation/jobs/{job_id}` | 查询逐位置结果和累计用量 |
| `POST` | `/v1/admin/generation/batches/{batch_id}/pause` | 暂停运行批次 |
| `POST` | `/v1/admin/generation/batches/{batch_id}/resume` | 将暂停批次恢复为运行态 |
| `POST` | `/v1/admin/generation/batches/{batch_id}/cancel` | 取消批次 |
| `POST` | `/v1/admin/generation/batches/{batch_id}/validate` | 重新执行候选题验证流水线 |

## 4. 创建生成任务请求示例

```json
{
  "idempotency_scope": "problem-bank.uc-c1-function-limit",
  "idempotency_key": "2026-10-06-seed-batch-001",
  "mother_problem_ids": ["<可信母题 ID 1>", "<可信母题 ID 2>"],
  "requested_count": 20,
  "subject": "math",
  "grade_band": "university",
  "topic_code": "UC.C1",
  "problem_type": "function_limit",
  "knowledge_point_codes": ["UC.C1", "UC.C1.LIMIT.FUNC_LIMIT"],
  "capability_point_codes": [],
  "allowed_derivation_types": [
    "parameter_change",
    "condition_change",
    "context_change"
  ],
  "difficulty": {"minimum": 2, "maximum": 4},
  "language": "zh-CN",
  "model_version_id": "<启用的模型版本 ID>",
  "prompt_version_id": "<启用的 question_generation 提示版本 ID>",
  "verifier_profile": "<大学高数题型对应的验证器配置>",
  "auto_validate": false,
  "constraints": {
    "domains": ["reals"],
    "preserve_answer_type": true,
    "preserve_solution_count": false,
    "require_unique_answer": false,
    "require_programmatic_verification": true,
    "allow_new_knowledge_points": false,
    "prohibited_terms": []
  },
  "budget": {
    "max_execution_attempts": 3,
    "max_model_calls": 80,
    "max_revision_rounds": 2,
    "max_input_tokens": 100000,
    "max_output_tokens": 50000,
    "max_total_tokens": 150000,
    "max_cost_minor_units": 10000,
    "currency": "USD",
    "max_duration_seconds": 900,
    "max_candidates": 20
  }
}
```

`subject` 和 `grade_band` 在 MVP 中只能是 `math` 和 `university`。`allowed_derivation_types` 必须使用领域枚举中已经定义的变式类型。当前大学高数确定性验证配置尚未完成，因此必须设置 `auto_validate=false`；不得用历史 `quadratic-v1` 代替并自动准入。

## 相关代码

- [生成管理 API](../../../../app/api/routes/admin_generation.py)
- [题目生成服务](../../../../app/services/question_generation.py)
- [生成管理服务](../../../../app/services/generation_admin.py)
