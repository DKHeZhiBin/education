# 相似题生成 API

## 1. 创建知识点相似题会话

```http
POST /v1/tutoring/knowledge-example-practice
Authorization: Bearer <student_access_token>
Content-Type: application/json
```

该接口从已发布的知识点题型内容生成一题 `session_only` 相似练习，并在生成、MPR 关系复核和会话初始化全部完成后返回 `CreateSessionResponse`。当前为同步接口。

### 1.1 请求

```json
{
  "knowledge_point_code": "UC.C1.CONTINUITY.DISCUSSION",
  "content_key": "discuss-continuity-and-discontinuities",
  "difficulty": "medium",
  "llm_model_id": null,
  "client_request_id": "client-generated-uuid"
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `knowledge_point_code` | 是 | 数据库知识点稳定编码 |
| `content_key` | 是 | 该知识点下已发布 `problem_type` 内容键 |
| `difficulty` | 否 | `easy`、`medium`、`hard`；默认 `medium`。旧值 `easier`、`same`、`harder` 会分别归一化 |
| `llm_model_id` | 否 | 用户选择的可用模型；为空时使用当前默认模型 |
| `client_request_id` | 是 | 客户端请求标识；当前会保存进会话证据，完整 Redis 幂等 Job 仍在 TODO 中 |

客户端只选择难度。后端使用固定映射决定目标 S/M/T、候选数量和质量门槛：

| 难度 | 目标关系与教学目标 | 候选数 | 质量门槛 |
| --- | --- | ---: | ---: |
| `easy` | `S1 + M1 + T2` | 1 | 72 |
| `medium` | `S2 + M2 + T1` | 2 | 78 |
| `hard` | `S3 + M3 + T4` | 3 | 82 |

请求中的目标 S/M 只用于指导生成。最终采用的实际 S/M 来自隔离的 `MPR-Relation` 复核，二者不一致时请求失败。

### 1.2 成功响应

成功返回 `201 Created` 和现有 `CreateSessionResponse`：

```json
{
  "session": {
    "id": "session-uuid",
    "question": "生成的题面",
    "status": "diagnosing",
    "artifacts": []
  },
  "reply": {
    "action": "diagnose",
    "text": "题目与第一步方向提示",
    "can_show_full_solution": false
  },
  "run_id": "run-uuid",
  "trace": [],
  "duration_ms": 0,
  "degraded": false,
  "degradation_code": null,
  "degradation_reason": null
}
```

响应 DTO 没有因为 MPR 改造而变化。完整母题 MPR、候选 MPR 和关系证据保存在会话的 `constrained_similar_practice` artifact 中。

### 1.3 会话证据

artifact 的 `payload` 至少包含：

```json
{
  "origin": "runtime_generated",
  "visibility": "session_only",
  "source_knowledge_point_code": "UC.C1.CONTINUITY.DISCUSSION",
  "source_content_key": "discuss-continuity-and-discontinuities",
  "generator": "knowledge_example_mpr_v1:deepseek/deepseek-flash",
  "structure_level": "S2",
  "reasoning_level": "M2",
  "teaching_goal": "T1",
  "mother_mpr": {},
  "candidate_mpr": {},
  "mpr_relation": {
    "relation_type": "variant_of",
    "structure_level": "S2",
    "reasoning_level": "M2",
    "confidence": 0.9,
    "review_status": "accepted"
  }
}
```

`structure_level` 和 `reasoning_level` 是已经通过独立复核的实际关系，不是生成器自报值。

## 2. 主要错误

错误响应统一使用：

```json
{
  "detail": {
    "code": "similar_problem_constraints_unsatisfied",
    "message": "当前学习范围内暂时无法生成合适的相似题……",
    "retryable": false
  }
}
```

| HTTP | `code` | 场景 |
| ---: | --- | --- |
| 401 | 认证错误代码 | Token 缺失、过期或无效 |
| 403 | 角色错误代码 | 当前用户不是学生 |
| 404 | `knowledge_example_unavailable` | 知识点内容不存在、未发布或不是可用题型 |
| 422 | `similar_problem_constraints_unsatisfied` | 所有候选均因数学、条件、实际 S/M、验证覆盖或质量门槛失败 |
| 422 | `llm_model_unavailable` | 指定模型不存在或不可用 |
| 503 | `agent_budget_exceeded` | 本轮多 Agent 调用超过运行预算，可稍后重试 |
| 503 | `session_coordination_unavailable` | Redis 协调能力不可用，可复用同一请求重试 |

MPR 关系为 `UNKNOWN`、`review_required`，或置信度低于 `0.65` 时统一视为候选不合格。接口不会把请求目标 S/M 当成实际判定结果，也不会返回未通过的兜底题。

## 3. 当前限制

- 当前同步等待包含母题 MPR、1—3 道候选生成、逐题关系复核和完整辅导会话初始化。
- `client_request_id` 已记录，但异步 Job 和 Redis 请求级幂等尚未实现。
- 会话级 AI 复核不能替代正式题库的确定性验证和完整准入。
- 生成题不会写入 MySQL 正式题库、关键词索引或 Qdrant。

性能与异步接口计划见[相似题生成性能优化方案](./SIMILAR_PRACTICE_PERFORMANCE_OPTIMIZATION.md)，MPR 字段见[MPR 数据模型](./MPR_DATA_MODEL.md)。
