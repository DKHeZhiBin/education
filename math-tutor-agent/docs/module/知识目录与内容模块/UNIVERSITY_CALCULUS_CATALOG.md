# 大学高等数学第一版目录

## 导入范围

版本 `2026.1` 包含 7 个后台可维护目录：

1. 函数、极限与连续；
2. 一元函数微分学；
3. 一元函数积分学；
4. 向量代数和空间解析几何；
5. 多元函数微分学；
6. 多元函数积分学；
7. 无穷级数。

第一版共包含 83 个知识点和 73 条先修关系。每章有一个根节点，章内主题作为子节点。关系图只保存实际影响学习顺序的边，不要求所有节点互连。

## 层级分类约定

大学高数目录按统一规则维护：一级章节根节点和二级主题节点分类为“核心”，三级及更深的具体知识点分类为“基础”。这里的分类只表示目录角色，不表示题目难度或学生掌握程度。调整父级导致知识点层级变化时，需要同步修改分类。

## 内容维护边界

目录种子只初始化目录、节点层级和先修关系。知识正文直接保存在 MySQL，并通过管理台维护；未经确认的正文保持为 `draft`，不会进入学生端的已发布内容。

第一章“函数、极限与连续”已经建立首批基础知识点内容种子，范围以数据库中当前分类为 `foundation` 的节点为准：

1. 数列极限；
2. 函数极限；
3. 无穷小与无穷大；
4. 极限运算法则；
5. 闭区间上连续函数的性质。

每个知识点首批各包含一条定义、性质、定理、公式和题型，共 25 条，初始状态统一为 `draft`。管理员应在管理台检查数学表述和展示效果，再逐条发布。

## 版本文件

第一章题库的可信母题、AI 变式生成、题型验证器和质量门槛规划见
[大学高数第一章题库建设与 AI 生成准入方案](../题库生产与治理模块/UNIVERSITY_CALCULUS_CHAPTER1_QUESTION_BANK.md)。

数据文件：`app/catalogs/data/university_calculus_managed.v1.json`

该文件保存首次导入的可追溯快照。数据库导入后可在管理台继续维护；重新执行导入会按稳定编码同步这份第一版快照。

## 导入命令

```bash
cd math-tutor-agent
.venv/bin/python -m app.managed_catalog_cli --validate-only
.venv/bin/python -m app.managed_catalog_cli
```

默认以 `admin.demo@example.com` 记录导入审计。其他环境应通过 `--actor-email` 指定真实管理员。

## 相关代码

- [大学高数目录数据](../../../app/catalogs/data/university_calculus_managed.v1.json)
- [受管目录种子导入](../../../app/catalogs/managed_seed.py)
- [当前 MySQL 结构基线](../../../migrations/versions/20261031_0035_current_schema_baseline.py)
- [产品范围常量](../../../app/core/product_scope.py)
- [学生端知识星图](../../../../src/features/knowledge/KnowledgePlanetPage.tsx)
