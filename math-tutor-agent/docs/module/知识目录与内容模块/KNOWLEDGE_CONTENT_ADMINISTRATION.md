# 知识星图与知识内容管理

知识目录、知识点、父级编码和内容键的具体命名方式见 [知识目录与知识点命名规范](./KNOWLEDGE_POINT_NAMING.md)。

## 1. 目标

知识星图的节点、先修关系以及节点下的定义、性质、定理、公式和题型由后台管理员维护。学生端只读取已启用节点与已发布内容，不在前端源码中保存业务数据。

管理前端位于仓库根目录的 `knowledge-admin/`，是独立的 React + TypeScript + Vite 工程，默认端口为 `5174`。它复用现有 FastAPI、MySQL 和身份认证，不与学生端页面和构建产物混合。

## 2. 数据对象

### `knowledge_catalogs`

保存一个可发布的知识目录版本，包括目录编码、版本、标题、学科、学段、主题和状态。`code + version` 唯一，`version_lock` 用于避免并发编辑覆盖。

### `knowledge_points`

现有知识点表增加：

- `catalog_id`：所属知识目录；
- `version_lock`：管理端乐观锁版本。

节点仍保存编码、名称、说明、分类、父节点、顺序和启用状态。学生知识星图继续从本表读取启用节点。

### `knowledge_point_prerequisites`

保存“学习目标知识点之前，需要掌握哪个知识点”，包括关系强度、掌握程度和关系说明。管理服务禁止自引用和循环依赖。

### `knowledge_point_contents`

每条内容属于一个知识点，`content_type` 只能是：

| 类型 | 含义 |
| --- | --- |
| `definition` | 定义 |
| `property` | 性质 |
| `theorem` | 定理 |
| `formula` | 公式 |
| `problem_type` | 题型 |

正文使用 Markdown，公式单独保存 LaTeX，扩展字段使用 `structured_json`。题型内容还提供 `solution_framework_json`，每个步骤由“步骤标题、框架思路、对应解题步骤、关键公式”组成。框架思路说明为什么采用当前方法，对应解题步骤说明该方法如何落到当前例题；二者始终成对保存和展示。

状态为 `draft`、`published` 或 `archived`；学生接口只返回 `published`。本系统的知识内容只服务于 AI 思维引导，因此不保存来源名称、来源版本和来源链接。

### `knowledge_admin_audits`

保存管理员、动作、对象、修改前后快照和时间。内容删除采用归档，避免失去历史。

## 3. 管理 API

所有接口位于 `/v1/admin/curriculum`，需要 `admin` 身份：

- `GET /dashboard`：概览统计；
- `GET|POST|PUT /catalogs`：目录查询、新增和更新；
- `GET|POST|PUT /points`：知识点查询、新增和更新；
- `DELETE /points/{point_id}`：安全删除知识点；存在子节点时拒绝，成功后隐藏节点、移除先修边并归档内容；
- `POST /points/bulk-delete`：批量安全删除；父节点的全部启用子节点都在本批选择中时允许整组删除，否则整批回滚；
- `GET|PUT|DELETE /relations`：先修关系维护；
- `GET /contents`：内容筛选；
- `POST /points/{point_id}/contents`：新增内容；
- `PUT|DELETE /contents/{content_id}`：更新或归档内容。

目录删除使用 `DELETE /catalogs/{catalog_id}`，仅允许删除不包含知识点的空目录。该约束用于避免一次误操作清空整章。知识点删除采用保留历史引用的安全删除，不物理清除已有学习记录。

面向学生的只读接口包括：

- `GET /v1/curriculum/catalogs`：返回学生端可选择的已发布目录；
- `GET /v1/curriculum/knowledge-graph`：返回目录内启用节点及真实先修关系；
- `GET /v1/curriculum/knowledge-points/{code}`：返回节点的已发布内容、直接先修和直接后续关系。

学生端知识星图、目录选择器和通用知识点详情页均调用以上接口。前端不再保留泰勒公式等知识点的静态正文和静态星图节点；管理员在 MySQL 中修改并发布后，学生端重新加载即可看到结果。

## 4. 静态目录迁移

原有 JSON 目录继续作为历史数据导入和本地初始化来源。运行时星图节点与关系一直从 MySQL 读取。根节点关联到 `knowledge_catalogs` 后，星图标题、目录编码和版本也从 MySQL 读取；未关联的旧数据暂时使用 JSON 元数据兜底，便于逐批迁移。

## 5. 发布流程

1. 管理员创建目录或选择现有目录。
2. 新建知识点、设置父节点与展示顺序。
3. 建立先修关系。
4. 为节点编辑五类内容；题型可以另外添加、排序和删除结构化解题框架步骤。
5. 确认正文和公式后改为已发布。
6. 学生端读取已启用节点和已发布内容。
7. 过期内容执行归档，审计记录永久保留。

### 内容数据来源

定义、性质、定理、公式和题型正文直接保存在 MySQL 的 `knowledge_point_contents` 表中。管理页面通过后台 API 读写该表，不使用本地 JSON 或前端静态数据作为知识正文来源。管理员新增、修改、发布和归档内容时，系统同时记录管理审计。

## 6. 数据库升级

知识内容基础表、题型框架以及数学思想与方法表均由当前 MySQL 结构基线创建。数学思想与方法的独立数据模型和管理流程见 [数学思想与方法数据管理](./THINKING_METHOD_ADMINISTRATION.md)：

```bash
cd math-tutor-agent
uv run alembic upgrade head
```

升级不会自动改写现有知识点。管理员可在管理台逐步把节点归入受管目录。

## 相关代码

- [管理端领域 DTO](../../../app/domain/curriculum_admin.py)
- [知识内容模型](../../../app/models/knowledge_content.py)
- [知识管理 Repository](../../../app/repositories/curriculum_admin.py)
- [知识管理服务](../../../app/services/curriculum_admin.py)
- [知识管理 API](../../../app/api/routes/admin_curriculum.py)
- [管理端知识点页面](../../../../knowledge-admin/src/features/points/KnowledgePointsPage.tsx)
- [学生端知识点详情页](../../../../src/features/knowledge/KnowledgePointDetailPage.tsx)
