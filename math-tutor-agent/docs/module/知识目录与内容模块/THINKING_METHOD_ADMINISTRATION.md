# 数学思想与方法数据管理

## 1. 目标

数学思想分类、具体方法、技巧及详情正文统一保存在 MySQL 中。学生端不再使用前端常量作为业务数据来源；管理员发布、归档或调整顺序后，学生端重新加载即可看到结果。

首批目录保留原有八类思想，并新增“逻辑与证明”“计数与组合”。参考书目录中的 72 个方法名称按层级整合：已有同名方法复用现有稳定编码，其余方法作为可独立维护的具体技巧录入。所有说明和例题均由本项目重新编写，不复制参考书正文。

## 2. 数据对象

### `thinking_method_categories`

保存顶层思想分类：稳定编码、名称、符号、思想定位、说明、学习提醒、显示顺序、发布状态和乐观锁版本。

### `thinking_methods`

保存具体方法或技巧：

- `code`：路由和外部引用使用的稳定编码；
- `category_id`：所属思想分类；
- `parent_method_id`：可选上级方法，用于“思想 → 策略 → 技巧”的层级；
- `kind`：`thought`、`strategy`、`technique` 或 `theorem_tool`；
- `level`：入门、深化或进阶；
- `grade_bands_json`：适用学段；
- `domain_tags_json`：适用知识领域；
- `aliases_json`：搜索别名；
- `detail_json`：详情页的定义、识别信号、步骤、例题、误用、先修和迁移练习；
- `status`：草稿、已发布或已归档；
- `version_lock`：避免多人编辑时互相覆盖。

`detail_json` 是结构化教学正文，不是前端 Mock。管理端修改后直接写入 MySQL，学生接口只返回已发布记录。

## 3. 接口与页面

学生端接口：

- `GET /v1/curriculum/thinking-methods`：读取已发布分类及方法；
- `GET /v1/curriculum/thinking-methods/{code}`：读取一个方法详情。

管理端接口位于 `/v1/admin/thinking-methods`，提供分类和方法的查询、新增、更新、归档。所有写操作要求管理员身份并记录到 `knowledge_admin_audits`。

独立管理台 `knowledge-admin/` 新增“思想与方法”菜单。分类可维护名称、符号、说明和顺序；方法可筛选分类与状态，并维护层级、学段、标签、别名和结构化详情。

## 4. 发布规则

1. 新建内容默认为草稿。
2. 只有分类和方法都为 `published` 时，学生端才展示该方法。
3. 归档方法后，学生端立即停止展示；其子方法会解除上级关系，避免孤立引用。
4. 分类下仍有未归档方法时禁止归档分类。
5. 稳定编码一旦被页面或 Agent 引用，后续只修改显示名称，不随意修改编码。

## 5. 数据库升级

当前结构基线创建两张表，并写入首批十类目录、原系统方法、参考目录方法及已经整理的完整方法讲解：

```bash
cd math-tutor-agent
uv run alembic upgrade head
```

升级后，原前端静态目录文件不再参与运行。

## 相关代码

- [思想方法领域对象](../../../app/domain/thinking_methods.py)
- [思想方法数据模型](../../../app/models/thinking_method.py)
- [思想方法 Repository](../../../app/repositories/thinking_methods.py)
- [思想方法管理服务](../../../app/services/thinking_methods.py)
- [思想方法管理 API](../../../app/api/routes/admin_thinking_methods.py)
- [管理端思想方法页面](../../../../knowledge-admin/src/features/methods/ThinkingMethodsPage.tsx)
- [学生端思想方法页面](../../../../src/features/knowledge/ThinkingMethodsPage.tsx)
