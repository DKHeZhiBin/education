# MySQL 数据库迁移流程

## 1. 目标

项目使用 Alembic 管理 MySQL 8.0 表结构。应用代码不调用 `Base.metadata.create_all()`，也不会在启动时自动修改数据库。数据库变更必须经过版本化迁移，以便开发、预发布和生产环境使用同一条升级路径。

连接地址只从 `.env` 的 `DATABASE_URL` 读取，`alembic.ini` 不保存账号和密码。

## 2. 首次建立数据库

先在 MySQL 中创建数据库和权限受限的应用账号，然后在 `math-tutor-agent/.env` 配置：

```dotenv
DATABASE_URL=mysql+pymysql://math_tutor:password@localhost:3306/math_tutor?charset=utf8mb4
```

从 `math-tutor-agent` 目录执行：

```bash
alembic current
alembic upgrade head
alembic current
```

初始迁移会创建用户、学生/家长、学习会话、消息、Agent 运行轨迹、学习记录、知识点、复习、报告和媒体元数据表，同时创建外键、唯一约束、检查约束和索引。后续 `20260928_0002` 迁移增加邮箱、密码哈希、令牌版本和最近登录时间；`20260928_0003` 增加邮箱验证状态、一次性账号操作令牌和可轮换 Refresh Session；`20260930_0004` 增加 RAG 来源、教材版本、知识文档、切片、题目和题解表；`20261002_0005` 增加能力点与先修关系；`20261002_0006` 扩展题目；`20261002_0007` 扩展题解；`20261002_0008` 增加生成批次、模型/提示/验证器版本和准入证据；`20261003_0009` 增加题目状态版本、修订计数与流转历史；`20261003_0010` 增加逻辑文档键、版本唯一约束和切片哈希索引；`20261003_0011` 增加 QuestionGenerationJob、生成预算与暂停状态；`20261003_0012` 增加不可变批次管理事件；`20261003_0013` 增加文档、切片和题目的统一教育内容标签；`20261003_0014` 增加题解步骤、错误模式和四级提示关联；`20261004_0015` 增加统一生产检索投影与 MySQL ngram 全文索引；`20261004_0016` 为索引 payload 增加验证覆盖、验证器版本和生成批次溯源；`20261004_0017` 增加可恢复的生产索引删除与重建任务；`20261005_0018` 增加知识索引 generation 状态，用于 Redis 检索缓存的可靠失效；`20261005_0019` 增加内容问题审计表和学习会话题库绑定，用于自动停用与重新验证。

`learning_sessions.version` 已包含在初始迁移中。本轮只启用 Repository 的原子版本比较与冲突处理，因此不需要新增 Alembic revision。

## 2.1 RAG 知识结构升级

RAG 基础迁移文件为：

```text
migrations/versions/20260930_0004_add_rag_knowledge_schema.py
```

它依赖 `20260928_0003`，按以下顺序创建空表：

```text
source_references
  → curriculum_versions
  → knowledge_documents
  → document_chunks
  → knowledge_problems
  → knowledge_solutions
```

该迁移只增加表、外键、检查约束、唯一约束和索引，不导入教材内容，不创建向量索引，也不更改现有用户和教学数据。可以先执行数据库升级，并继续保持：

文档逻辑键与版本唯一性由后续 `20261003_0010_enforce_document_versions.py` 补充，部署新摄取命令前应直接升级到当前 head。

```dotenv
RAG_ENABLED=false
```

推荐升级步骤：

```bash
alembic current
alembic upgrade 20260930_0004
alembic current
```

确认当前版本为 `20260930_0004` 后，再部署依赖知识表的导入程序。首次导入必须按来源、教材版本、文档、切片、题目、题解的依赖顺序进行。

正式启用 RAG 之前还必须完成：

1. 导入合法且可追溯的来源记录；
2. 完成内容审核并把合格文档标为 `approved`；
3. 建立向量或关键词索引；
4. 确认索引记录可以反查 MySQL 的文档、切片和来源；
5. 配置已注册的 `RAG_PROVIDER` 后再设置 `RAG_ENABLED=true`。

## 2.2 课程目录升级与导入

课程目录迁移文件为：

```text
migrations/versions/20261002_0005_add_curriculum_catalog.py
```

升级后再执行版本化目录导入：

```bash
alembic upgrade 20261002_0005
math-tutor-catalog --validate-only
math-tutor-catalog
```

Alembic 只建立数据结构，不自动写入学科目录。`math-tutor-catalog` 根据稳定编码幂等同步首批“一元二次方程”目录，因此可以在内容更新后重新运行。回滚 `20261002_0005` 会删除全部能力点和先修关系，并移除知识点新增字段；执行前必须备份目录关系数据。

## 2.3 题目结构升级

题目结构迁移文件为：

```text
migrations/versions/20261002_0006_extend_knowledge_problems.py
```

执行：

```bash
alembic upgrade 20261002_0006
```

迁移会为已有题目写入空的显式条件、隐式条件和难度来源列表，并将 `content_status` 设为 `candidate`。已有 `review_status` 不会自动映射为 `approved`，因为旧记录尚未经过新的结构化和自动准入流程。母题外键采用 `RESTRICT`；删除母题前必须先重新挂接或退役其变式题。

## 2.4 题解结构升级

题解结构迁移文件为：

```text
migrations/versions/20261002_0007_extend_knowledge_solutions.py
```

执行：

```bash
alembic upgrade 20261002_0007
```

迁移为已有题解写入空步骤、空突破口和 `none` 验证覆盖。因为旧验证记录没有步骤级覆盖证据，迁移会把原状态保存到 `metadata_json.pre_structure_verification_status`，并将当前 `verification_status` 重置为 `unverified`。需要重新生成结构化步骤并完成验证后，才能恢复为 `partial` 或 `verified`。回滚时会恢复保存的旧状态并移除临时元数据字段。

## 2.5 生成审计对象升级

迁移文件为：

```text
migrations/versions/20261002_0008_add_generation_audit_objects.py
```

执行：

```bash
alembic upgrade 20261002_0008
```

迁移创建 `model_versions`、`prompt_versions`、`verifier_versions`、`generation_batches` 和 `admission_evidence`，并为 `knowledge_problems` 增加可空的 `generation_batch_id`。已有题目不会自动归入虚构批次。版本、批次、题目和证据使用限制删除外键，防止审计链被级联清除。

## 2.6 题目生命周期持久化

迁移文件为：

```text
migrations/versions/20261003_0009_add_problem_lifecycle_persistence.py
```

执行：

```bash
alembic upgrade 20261003_0009
```

迁移为题目增加 `revision_attempts`、`status_version` 和 `status_changed_at`，并创建 `problem_status_transitions`。已有题目的修订次数设为 `0`、状态版本设为 `1`，状态变化时间采用原记录更新时间。迁移不会伪造历史流转记录；只有升级后通过 Repository 完成的真实状态变化才会写入历史表。

### 回滚限制

`alembic downgrade 20260928_0003` 会删除全部六张 RAG 表及其中内容。只允许在空白开发环境，或确认已经备份且不再被索引使用时执行。向量数据库中的对应索引不由 Alembic 自动删除；回滚后必须由知识索引运维流程清理孤立 point。

## 3. 日常升级流程

1. 先修改 `app/models` 下的 SQLAlchemy 模型。
2. 基于模型生成候选迁移：

   ```bash
   alembic revision --autogenerate -m "describe schema change"
   ```

3. 人工检查生成文件，重点确认：

   - 升级和回滚顺序；
   - MySQL 类型、无符号整数和 `DATETIME(6)`；
   - 外键的 `ON DELETE` 行为；
   - 索引、唯一约束和约束名称；
   - 新增非空列是否有数据回填步骤；
   - 是否存在误删表、误删列或不可逆数据转换。

4. 在开发数据库执行升级并检查 `alembic current`。
5. 应用和迁移一起进入预发布环境。
6. 生产发布时先备份数据库，再执行 `alembic upgrade head`，成功后部署依赖新结构的应用版本。

不要直接把 autogenerate 输出作为最终迁移。Alembic 能比较表结构，但不能理解业务数据迁移、兼容窗口和安全回填顺序。

## 4. 查看迁移状态

```bash
alembic current
alembic heads
alembic history --verbose
alembic show head
```

CI 或部署流程应执行：

```bash
alembic upgrade head
alembic current
```

并确认数据库只存在一个迁移 head。

## 5. 回滚

回滚一个版本：

```bash
alembic downgrade -1
```

回滚到指定 revision：

```bash
alembic downgrade <revision_id>
```

初始迁移的 downgrade 会删除项目全部业务表，只能用于空白开发环境。RAG 迁移的 downgrade 会删除知识库内容，且不会清理外部向量索引。生产环境不得直接执行这些破坏性回滚；应从备份恢复，或编写保留数据的修复迁移。

## 6. 已有数据库接入

只有当现有数据库结构经过人工核对，确认与初始迁移创建的结构完全一致时，才可以执行：

```bash
alembic stamp 20260928_0001
```

`stamp` 只写入版本号，不创建或修改表。不能用它跳过结构差异。

## 7. 生产变更规则

- 优先采用“扩展、迁移数据、切换代码、最后清理”的多版本流程。
- 大表新增索引或改列前评估锁表时间，并根据 MySQL 环境选择在线 DDL 策略。
- 删除列之前，先发布不再读取该列的应用版本。
- 新增非空列时，先允许为空或提供安全默认值，回填历史数据后再收紧约束。
- 每个迁移 revision 一旦进入共享环境便不再修改；后续修正创建新的 revision。
- 迁移日志不得输出数据库密码或学生隐私数据。

## 8. 文档版本唯一性与切片去重索引

`20261003_0010` 为 `knowledge_documents` 增加非空 `document_key`，用新的 `source_reference_id + document_key + version_label` 唯一约束替代旧的版本/内容约束；同时为 `document_chunks.content_hash` 增加普通索引。历史文档按“来源 ID + 标题”生成稳定回填键，后续摄取清单必须显式提供逻辑文档键。

该迁移不修改已有文档状态，也不自动删除重复切片。新的摄取流程负责阻止版本标签被静默覆盖，并在后续导入中记录跨文档相同切片。

## 9. 候选题生成 Job

`20261003_0011` 创建 `question_generation_jobs`，与 `generation_batches` 建立一对一关系，并为批次增加 `paused` 状态。迁移同时收紧批次数量语义：批准数与隔离数不能超过已生成数，已生成数与生成失败数不能超过请求数。

迁移会为缺少 `started_at` 的历史执行批次使用创建或结束时间回填，并在 `config_json.started_at_backfilled_by_0011` 留痕；若非终态批次错误地带有结束时间，会先把原值保存到 `config_json.legacy_nonterminal_finished_at` 再清空。

旧数据若存在 `generated_count + failed_count > requested_count`，迁移会先把原 `failed_count` 保存到 `config_json.legacy_failed_count`，再按新的“未产生候选的位置数”语义重新计算 `failed_count`。该兼容记录不会被自动删除。

降级时，新语义下无法满足旧约束的失败计数会先保存为 `config_json.pre_downgrade_failed_count`；处于 `paused` 的批次会保存原状态并转换为带结束时间的 `cancelled`。这些转换避免回滚因旧约束无法表达新数据而中断。

## 10. 批次管理事件

`20261003_0012` 创建 `generation_batch_management_events`，记录暂停、恢复、取消、重试关联和批准内容撤回。批次及关联重试批次均使用限制删除外键，防止物理删除破坏审计链。

## 11. 教育内容标签

`20261003_0013` 为文档增加精确年级、题型、难度来源和内容类型集合，为切片增加教材版本、学段、精确年级、题型和难度来源快照，为题目增加教材版本、精确年级和内容类型。迁移从文档回填已有切片和题目的可推导标签，无法可靠推导的年级、题型与难度来源保持空列表，等待重新标注。

迁移后可重新执行可信母题导入；导入器会在不改写已批准题目正文和状态的前提下，为现有 ORCCA 母题补齐 `grade_9`、教材版本、题型、内容类型和难度来源标签。

## 12. 已批准内容定期复核

`20261006_0020` 创建复核策略、执行批次和逐题结果三张表。策略引用已经登记的模型、提示词和验证器版本；批次和逐题记录保存证据引用与错误详情。

该迁移只创建表和约束，不会立即停用题目、调用模型或修改 Qdrant。升级后需要显式创建策略，并由 `math-tutor-revalidate run-due` 或对应管理 API 触发执行。完整流程见 `docs/PERIODIC_REVALIDATION.md`。
