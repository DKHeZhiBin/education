# 生产索引删除与重建流程

## 1. 目标

题目退役、重新验证和版本更新不能只修改 MySQL 状态。生产关键词索引和 Qdrant Point 必须一起退出，并留下可重试、可审计的维护记录。

`search_index_maintenance_jobs` 是外部索引维护 Outbox。业务事务只负责创建任务并立即把 MySQL 关键词投影标记为 `retired`；维护执行器随后删除 Qdrant Point，保存 `index_removal` 准入证据并推进题目状态。

## 2. 三种流程

### 2.1 题目退役

```text
indexed / approved
  → 创建 remove 任务
  → MySQL 投影立即 retired
  → 删除 Qdrant Point
  → 保存 index_removal 证据
  → 题目进入 retired
  → 任务 completed
```

`retired` 是终态，不能原地恢复。

### 2.2 重新验证

```text
indexed
  → 创建 rebuild 任务
  → 删除 MySQL/Qdrant 旧索引
  → 保存 index_removal 证据
  → 题目进入 quarantined
  → 任务 waiting_for_approval
  → quarantined → validating → approved
  → 维护执行器重新发布关键词和向量索引
  → approved → indexed
  → 任务 completed
```

旧索引删除后，确定性校验、独立解题和独立复核必须重新执行。维护任务不会自行批准内容。

### 2.3 版本更新

版本更新必须提供新的 `replacement_problem_id`：

```text
旧题 indexed
  → 删除旧索引并将旧题 retired
  → 等待新版本题目 approved
  → 为新题建立关键词和 Qdrant 索引
  → 新题 indexed
```

旧题及其证据继续保留，索引任务同时记录旧题 ID、新题 ID、旧内容哈希和目标索引版本。

## 3. 一致性与重试

- 创建任务时，MySQL 投影先变为 `retired`，关键词检索立即不可见；
- Qdrant 删除成功后才保存 `index_removal=passed`；
- 状态机只有看到删除证据且确认索引不活动时，才允许 `indexed` 进入 `quarantined` 或 `retired`；
- Point ID 删除是幂等操作，执行器可安全重放；
- 任务保存删除完成时间和重建完成时间；
- `deleting`、`rebuilding` 和 `failed` 任务会在下一次执行时恢复；
- 达到最大尝试次数后保持 `failed`，等待管理员检查；
- 异常只保存短错误类别，不保存连接信息、密钥或响应正文。

## 4. 管理命令

创建退役任务：

```bash
math-tutor-index retire <problem_id> --reason "题目已停止使用"
```

创建重新验证任务：

```bash
math-tutor-index revalidate <problem_id> --reason "验证器规则升级"
```

替换内容版本：

```bash
math-tutor-index replace-version <old_problem_id> <new_problem_id> \
  --reason "发布新的题目版本"
```

执行任务和查看状态：

```bash
math-tutor-index maintain --limit 25
math-tutor-index maintenance-status <job_id>
```

生产环境应定期执行 `maintain`。任务处于 `waiting_for_approval` 时不会调用 Embedding，也不会重建未批准内容。

## 5. 配置

```dotenv
PRODUCTION_INDEX_MAINTENANCE_MAX_ATTEMPTS=5
PRODUCTION_INDEX_MAINTENANCE_LEASE_SECONDS=300
```

重建仍使用生产索引现有的 Embedding、Qdrant、索引版本和批大小配置。
