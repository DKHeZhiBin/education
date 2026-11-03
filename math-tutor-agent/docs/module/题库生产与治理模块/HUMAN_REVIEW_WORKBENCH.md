# 教师人工抽检工作台

## 1. 适用范围

人工抽检入口面向两类内容：

- `quarantined`：自动系统无法批准、确定性验证失败或验证覆盖不足的题目。
- 高价值题目：难度为 4–5、可信母题，或在 `metadata_json.high_value` 中被明确标记的题目。

该能力是可选模块。没有教师账号时，原有 AI 生成、自动验证、隔离和定期复核流程可以继续运行。

## 2. 权限

- `admin`：生成抽检队列，也可以领取和提交抽检。
- `teacher_reviewer`：查看、领取和提交抽检任务。
- 学生和家长不能访问工作台。

公开注册仍只允许学生和家长。教师账号应由管理员完成资质确认后，在内部账号管理流程中创建或授予 `teacher_reviewer` 角色，避免任何用户自行声明教师身份。

## 3. 数据对象

`human_review_tasks` 保存待审题目及题解的内容哈希、状态版本、入队原因、价值分和领取状态。同一内容版本存在待领取或已领取任务时不会重复入队；任务完成后仍可以按新的抽检批次再次审核。

`human_content_reviews` 保存不可变的教师提交记录，包括：

- 审核人账号；
- 题目和题解内容哈希；
- `approve`、`revision_required`、`quarantine` 或 `inconclusive` 结论；
- `full`、`partial` 或 `none` 覆盖级别；
- 结构化检查表、问题列表和总结；
- 对应 `qualified_human_review` 准入证据 ID。

任务使用 `version` 做乐观锁。题目或题解内容发生变化后，旧任务变为 `stale`，教师必须审核新版本。

## 4. 工作流程

```text
管理员筛选 quarantined / 高价值题目
  -> 创建版本化抽检任务
  -> 教师领取任务
  -> 对题干、条件、答案、步骤、教学标签和覆盖范围进行检查
  -> 提交结构化结论
  -> 写入 qualified_human_review 审计证据
  -> 错误结论触发生产索引停用和重新验证
  -> 隔离题目的通过结论进入规则化准入门统一处理
```

教师选择 `approve` 时必须声明 `full` 覆盖，并且任务必须绑定一个未变化的题解版本。这个结论可以为证明题或开放题提供权威人工覆盖证据。

教师通过不会直接把题目改成 `approved`。对于 `quarantined` 题目，系统先将其送回 `validating`，随后立即调用同一个规则化准入门。题目仍需满足来源许可、条件完整性、独立解题、确定性验证、查重、泄漏检查等现有准入要求。任何确定性失败都不能被人工意见覆盖。

教师提交 `revision_required` 或 `quarantine` 时，如果题目仍在 `approved/indexed`，系统会创建 `revalidation` 索引维护任务，停用 MySQL 关键词索引和 Qdrant 向量，并把内容重新送回验证链路。

## 5. 高价值评分

首版价值分用于排序，不参与自动准入：

| 因素 | 分值 |
| --- | ---: |
| 已处于 `quarantined` | 45 |
| 难度 4–5 | 25 |
| 可信母题 | 20 |
| 显式标记 `high_value` | 30 |

总分上限为 100。后续可以加入真实使用次数、学生错误集中度、课程核心程度和内容问题报告次数。

## 6. 管理 API

生成或刷新队列，仅管理员可调用：

```http
POST /v1/admin/human-reviews/queue/refresh
```

示例请求：

```json
{
  "include_quarantined": true,
  "include_high_value": true,
  "minimum_difficulty": 4,
  "limit": 50,
  "priority": 3,
  "review_requirements": {
    "check_answer": true,
    "check_solution_steps": true,
    "check_grade_fit": true
  }
}
```

教师工作台接口：

- `GET /v1/admin/human-reviews/tasks`：读取队列；`mine=true` 只返回自己领取的任务。
- `POST /v1/admin/human-reviews/tasks/{task_id}/claim`：按任务版本领取。
- `POST /v1/admin/human-reviews/tasks/{task_id}/reviews`：提交结构化结论。

提交示例：

```json
{
  "expected_version": 2,
  "decision": "approve",
  "coverage_level": "full",
  "checklist": {
    "conditions_complete": true,
    "answer_correct": true,
    "steps_valid": true,
    "grade_fit": true
  },
  "issues": [],
  "summary": "题目条件完整，答案和全部步骤正确，适合当前学段。"
}
```

## 7. 部署

执行迁移：

```bash
alembic upgrade head
```

迁移只创建任务和审核记录表，不会自动生成队列，也不会修改现有题目状态。部署后由管理员调用队列刷新接口；教师资源尚未接入时可以保持队列为空。

## 相关代码

- [人工抽检领域对象](../../../app/domain/human_review.py)
- [人工抽检数据库模型](../../../app/models/human_review.py)
- [人工抽检 Repository](../../../app/repositories/human_review.py)
- [人工抽检服务](../../../app/services/human_review.py)
- [人工抽检 API](../../../app/api/routes/admin_human_review.py)
