# 教材知识与学生历史检索边界

## 两个数据域

系统将检索拆为两个不能互换的 Provider：

| 数据域 | Provider | 数据来源 | 用途 | 缓存 |
| --- | --- | --- | --- | --- |
| `textbook` | `TextbookKnowledgeRetriever` | 已批准教材、课程标准、题目、题解及来源引用 | 题意背景、定理依据、同构结构、分级提示 | 可以进入按知识库版本失效的共享 Redis 缓存 |
| `student_private` | `StudentHistoryRetriever` | 当前学生自己的结构化学习记录 | 选择提示起点、避免重复无效解释、约束练习范围 | 当前版本不写共享 Redis，每次按学生 ID 从 MySQL 查询 |

教材检索不得访问 `learning_records`、`learning_record_knowledge`、会话消息或学生身份表。学生历史检索不得访问 Qdrant、教材文档、生产关键词索引，也不生成教材引用。

## 身份隔离

`StudentHistoryQuery.student_user_id` 只能由已经完成归属校验的 `TutoringSession.student_user_id` 生成，不能由聊天文本或前端自由提供。MySQL 查询固定包含：

```text
learning_records.student_user_id = 当前会话所有者
```

学生历史结果进入 Agent 前会移除学生 ID，只保留按知识点聚合的次数、错误次数、有效尝试、最高提示等级、最近掌握状态和最近证据摘要。

## Orchestrator 使用规则

- 公共教材上下文保存为 `retrieved_textbook_context` artifact。
- 个人历史上下文保存为 `retrieved_student_history` artifact。
- 公共检索结果可以生成来源引用；个人历史不能生成教材引用。
- 学情诊断仍只依据当前轮可观察作答；个人历史只帮助提示 Agent 选择表达和起点。
- 个人历史不能覆盖已校验解法、教材结论、提示披露等级或本轮诊断证据。
- 两个 DTO 使用固定 `data_scope` 字段，错误的数据域无法通过领域校验。

## 缓存规则

教材检索的 Redis Key 仍使用 `rag:query:*`，并随生产知识索引版本失效。学生历史当前不进入该缓存，因此不会出现学生 A 的历史通过公共查询摘要或热门查询缓存返回给学生 B 的情况。若未来增加个人缓存，Key 必须包含不可逆的学生作用域摘要，并在学习记录更新时单独失效。

## 相关代码

- [学生历史 Provider](../../../app/providers/student_history.py)
- [学生历史领域对象](../../../app/domain/student_history.py)
- [教材知识 Provider](../../../app/providers/knowledge.py)
- [教学上下文过滤边界](../../../app/retrieval/teaching_context.py)
