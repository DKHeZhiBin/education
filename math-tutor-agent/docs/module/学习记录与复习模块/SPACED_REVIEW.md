# 间隔复习与复习任务

## 1. 目标

复习任务基于真实完成的 `LearningRecord` 生成。系统保留原题、学生作答、错因、知识点、提示等级和有效尝试，不把一次复习结果直接解释成长期能力。

复习任务不使用独立的重复表。`learning_records.next_review_at` 表示任务到期时间，`review_attempts` 保存每次复习历史，二者共同构成可恢复的复习队列。

## 2. 首次复习

完成学习记录时按本轮掌握状态安排：

| 本轮状态 | 首次复习间隔 |
| --- | --- |
| `to_review` | 1 天 |
| `reviewing` | 3 天 |
| `mastered` | 14 天 |

升级迁移会为已有且尚未安排时间的学习记录补齐首次复习时间，不覆盖已经存在的计划。

## 3. 后续间隔

每次复习后增加 `review_count`，写入不可覆盖的 `ReviewAttempt`，再计算下一次时间：

- `incorrect`：1 天后再次复习，状态回到 `to_review`；
- `partial`：3 天后复习，状态为 `reviewing`；
- `correct`：按 1、3、7、14、30、60 天序列逐步拉长；
- 已掌握内容正确复习时，间隔至少为 14 天；
- 连续两次无提示正确才允许从复习中进入 `mastered`；
- 使用提示完成时保持 `reviewing`，不会因一次正确直接判定掌握。

间隔超过序列上限后保持 60 天。日期计算由 `app/mcp_tools/review_tools.py` 的确定性函数完成，HTTP 服务和 MCP Tool 复用同一规则。

## 4. API

读取当前学生已到期任务：

```http
GET /v1/tutoring/review-tasks?scope=due&limit=50
Authorization: Bearer <access-token>
```

`scope` 可选 `due`、`upcoming` 或 `all`。家长和管理员可以在已有授权范围内通过 `student_id` 读取，只有学生本人可以提交复习尝试。

记录一次复习：

```http
POST /v1/tutoring/review-tasks/{learning_record_id}/attempts
Authorization: Bearer <access-token>
Content-Type: application/json

{
  "answer_text": "x=2 或 x=-2",
  "result": "correct",
  "hint_level": 0,
  "session_id": null
}
```

响应返回本次尝试 ID、更新后的任务、下一次间隔和调度理由。若复习通过新的辅导会话完成，可填写属于同一学生的 `session_id`，形成可追溯关联。

## 5. 数据边界

- `ReviewAttempt` 只追加，不修改历史尝试；
- 学习记录的 `mastery_status` 表示当前复习调度状态；
- 知识点关联中的掌握状态保留原会话快照，不被后续复习覆盖；
- 跨题、跨知识点的长期掌握度需要后续聚合多条证据；
- 调度计算不调用 LLM，相同输入得到相同结果。

## 相关代码

- [复习领域对象](../../../app/domain/review.py)
- [复习 Repository](../../../app/repositories/reviews.py)
- [间隔复习确定性工具](../../../app/mcp_tools/review_tools.py)
- [学习与复习模型](../../../app/models/learning.py)
- [学生端复习页面](../../../../src/features/review/MistakesPage.tsx)
