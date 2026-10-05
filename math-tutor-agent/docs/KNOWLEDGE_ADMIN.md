# 题库管理查询与状态持久化

## 1. 组成

- `app/repositories/knowledge.py`：题目状态写入和管理查询；
- `app/services/knowledge_admin.py`：管理用例协调入口；
- `app/api/routes/admin_knowledge.py`：管理员 HTTP 接口；
- `problem_status_transitions`：不可变状态流转历史；
- `knowledge_problems.status_version`：状态乐观锁版本；
- `knowledge_problems.revision_attempts`：自动修订累计次数；
- `knowledge_problems.status_changed_at`：最近一次真实状态变化时间。

`problem_status_transitions.problem_id` 使用 `RESTRICT` 删除策略。有状态历史的题目不能直接物理删除，应流转到 `retired` 后继续保留审计链。

最大自动修订次数由 `KNOWLEDGE_PROBLEM_MAX_REVISION_ATTEMPTS` 配置，默认值为 `2`，允许范围为 1–2；候选题自动修订流程具有不可提高的两次硬上限。

所有接口都要求访问令牌中的用户角色为 `admin`。学生和家长账号返回 `403`。

## 2. 管理查询

### 状态汇总

```http
GET /v1/admin/knowledge/problems/status-summary
```

响应固定包含七个状态，即使某个状态当前数量为零也会返回。

### 题目列表

```http
GET /v1/admin/knowledge/problems
```

支持以下筛选参数：

- `statuses`：可重复传递多个内容状态；
- `subject`；
- `grade_band`；
- `problem_type`；
- `generation_batch_id`；
- `grade_code`；
- `content_type`；
- `curriculum_version_id`；
- `knowledge_point_code`；
- `difficulty_source`；
- `search`：题干包含搜索；
- `limit`、`offset`：分页。

列表按最近状态变化时间倒序排列，并返回来源与许可证、生成批次、修订次数和状态版本。

### 题目审计详情

```http
GET /v1/admin/knowledge/problems/{problem_id}
```

列表和详情返回内容类型、教材版本、知识点及难度来源类型。详情还包含结构化条件、目标、完整难度来源、题解数量、完整验证题解数量、全部准入证据、状态流转历史和 `audit_timeline`。时间线按顺序合并生成、检查、独立解题、工具验证、复核、修订、准入、索引和状态变化；每项保留来源记录 ID、版本引用、内容哈希、状态版本、公开摘要和结构化载荷。

## 3. 状态流转

```http
POST /v1/admin/knowledge/problems/{problem_id}/transitions
Content-Type: application/json

{
  "target_status": "validating",
  "expected_status_version": 1,
  "reason": null,
  "index_is_active": false
}
```

Repository 在事务中执行以下动作：

1. 锁定题目当前行，再锁定该题目的题解和准入证据范围；
2. 比较 `expected_status_version`；
3. 从数据库加载题目、题解和准入证据；
4. 计算结构完整性、来源权利证据和完整验证题解；
5. 调用 `ProblemContentStateMachine`；
6. 更新题目状态、修订次数和版本；
7. 追加一条 `problem_status_transitions` 记录；
8. 一次提交全部变化。

版本不一致返回 `409 status_version_conflict`。非法流转或准入门槛不完整也返回 `409`，并提供缺失条件与建议状态。相同状态请求为幂等空操作，不增加版本，也不写入虚假历史。

`index_is_active` 表示索引适配器对生产索引的即时确认结果。进入 `indexed` 还必须存在最新通过的 `index_sync` 证据；从 `indexed` 隔离或退役时必须存在最新通过的 `index_removal` 证据。

## 4. 来源权利门槛

Repository 不根据非空的 `license_name` 自动判断权利清晰。批准前必须存在最新且为 `passed` 的 `source_rights_clearance` 准入证据。证据应记录许可证、授权范围、来源 URL、核验时间和核验规则版本。

## 5. 并发规则

- 客户端读取详情后保存 `status_version`；
- 写入时提交该版本；
- Repository 同时使用数据库行锁和版本比较；
- 收到冲突后重新读取详情，根据最新证据重新决定目标状态；
- 禁止无条件重放旧的状态变更请求。
