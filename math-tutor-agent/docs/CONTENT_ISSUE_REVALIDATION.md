# 题目错误反馈与自动重新验证

## 1. 目标

当学生报告题目、答案或提示存在问题，或教学运行时发现同一道题的多个解法答案冲突时，系统必须先停止继续分发该题，再让当前内容版本重新通过完整验证。反馈本身是风险信号，不直接判断学生或系统哪一方正确。

## 2. 可信绑定

题库题目创建学习会话时，客户端传入可选的 `problem_id`。服务端读取题库中的标准题面，不采用客户端同时提交的题面覆盖题库内容，并在 `learning_sessions.knowledge_problem_id` 保存绑定。

学生反馈只能指向当前会话绑定的题库题目，或当前会话真实检索到且保存在 `retrieved_teaching_context` 中的题目。这样可以防止普通学生通过猜测 ID 停用未在本轮使用的题目。

## 3. 学生反馈接口

```http
POST /v1/tutoring/sessions/{session_id}/content-issues
```

```json
{
  "problem_id": "可选；会话只有一道可报告题目时可省略",
  "issue_type": "incorrect_answer",
  "description": "第二个根代回原方程不成立",
  "client_report_id": "前端生成的幂等键"
}
```

`issue_type` 支持 `incorrect_answer`、`incorrect_question`、`incorrect_hint`、`ambiguous_content`、`answer_conflict` 和 `other`。同一用户、会话、题目和 `client_report_id` 重放时返回同一记录。

## 4. 运行时冲突

Harness 每次保存会话后检查本轮最终 `solution_plan` 和 `verification_report`。只有会话已经绑定题库题目，且出现明确的 `answer_consistency=conflict` 或校验报告明确指出答案不一致时，才自动创建 `runtime_answer_conflict` 事件。无法程序确认的文字差异不会自动停用题目。

## 5. 停用与重验证流程

```text
学生反馈 / 运行时答案冲突
  → 写入 content_issue_reports
  → 将 MySQL 生产检索投影标记为 retired
  → 推进知识索引 generation，使旧 Redis 缓存立即不可达
  → 创建 revalidation 索引维护任务
  → 删除 Qdrant Point
  → indexed/approved → quarantined → validating
  → 等待完整验证证据和自动准入门重新批准
  → approved 后由维护任务重新建立索引，并把关联反馈标记为 resolved
```

Qdrant 暂时不可用时，维护任务保留为 `failed` 并可按既有重试规则继续执行；问题报告和 MySQL 关键词停用不会回滚。向量候选返回前还必须通过 MySQL 活动投影校验，因此已经标记为 `retired` 的投影即使暂时残留在 Qdrant 中，也不能进入教学上下文。

## 6. 证据隔离

进入 `validating` 时，题目元数据保存 `revalidation_started_status_version`。自动准入门只接受 `problem_status_version` 不早于该值的内容相关证据，包括条件完整性、独立解题、数学验证、重复和评估集泄漏检测、独立教学复核。

来源权利证据可以继续使用，因为题目内容版本未发生变化。旧的数学和教学证据继续保留用于审计，但不能让题目跳过本轮重新验证。

## 7. 审计对象

`content_issue_reports` 保存来源、问题类型、学生说明或运行时冲突摘要、会话、题目、幂等哈希、维护任务和处理状态。运行时证据只保存必要的解法 ID、候选答案和校验问题摘要，不保存模型完整推理过程。
