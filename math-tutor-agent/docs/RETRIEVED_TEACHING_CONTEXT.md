# RetrievedTeachingContext 结构化教学上下文

## 1. 目标

检索后端返回的文档切片只是召回候选，不能直接拼接到 Agent Prompt。`RetrievedTeachingContext` 负责把候选内容转换为有界、带来源、符合当前教学阶段的事实对象。

边界分为两层：

```text
向量库 / 关键词索引
        │
        ▼
RetrievedKnowledge              Provider 内部，含最多 2000 字符的原始候选摘录
        │  解析、归一化、去重、重排、披露检查
        ▼
RetrievedTeachingContext        系统边界，含查询、诊断和结构化教学对象
        │  to_agent_context()
        ▼
AgentTeachingContext            唯一允许写入 Agent Prompt 的 RAG 对象
```

`AgentTeachingContext` 不包含原始 `content`、检索查询、Provider 名称、候选数量、延迟或任意后端 metadata。

## 2. 结构化内容组

| 内容组 | 主要字段 | 数量上限 | 单项文本上限 |
| --- | --- | ---: | ---: |
| `concepts` | 概念编码、定义摘要、记号、先修知识 | 8 | 600 字符 |
| `principles` | 定理或公式摘要、适用条件、约束 | 8 | 700 字符 |
| `problem_patterns` | 题目结构、条件模式、目标模式、方法名 | 5 | 700 字符 |
| `solution_outlines` | 已验证方法、突破口、最多十个结构化步骤 | 3 | 每字段 800 字符以内 |
| `error_patterns` | 可观察错误信号、诊断问题、修复目标 | 6 | 600 字符 |
| `hints` | 已批准提示、等级、步骤和错误模式关联 | 4 | 1000 字符 |
| `source_facts` | 定义、课标要求、定理或来源事实 | 8 | 800 字符 |

每一项都必须带 `KnowledgeCitation`，至少能定位文档，通常还包含来源、版本、切片和章节定位。列表中的字符串也有单项长度限制，不能利用数组字段绕过上下文预算。

整个 Agent 上下文默认不得超过 12000 个序列化字符，最大可配置值为 24000。超出预算时 Provider 必须先裁剪和重排，再构建对象；Schema 不会静默截断。

## 3. 用途白名单

| `purpose` | 允许内容 | 禁止内容 |
| --- | --- | --- |
| `problem_understanding` | 概念、原理、题目结构 | 解法、错误模式、提示、完整来源事实 |
| `solution_analysis` | 概念、原理、题目结构、解法轮廓、错误模式 | 提示蓝图、来源查询结果 |
| `hint_teaching` | 当前等级允许的概念、原理、结构、错误模式和提示 | 超过当前等级的内容 |
| `source_lookup` | `source_facts` | 其他全部教学对象 |

`status=success` 时必须至少有一个结构化对象。`disabled` 和 `no_results` 不允许携带教学内容；`degraded` 可以返回部分结果，同时在 `limitations` 中说明限制。

## 4. 四级提示披露

`purpose=hint_teaching` 时，`KnowledgeQuery.hint_level` 必填。

每个概念、原理、题型结构和错误模式都有 `disclosure_level`。只有 `disclosure_level <= hint_level` 的对象可以进入上下文。

- 一级不允许包含公式或方法名；
- 二级可以包含一个关键关系或方法名称；
- 三级仍不允许接收完整解法轮廓，只能读取已批准的三级提示；
- 四级可以读取 `solution_outlines`；其中最终答案只有在 `verification_level=full` 时才允许出现；
- 提示蓝图的等级必须与查询等级完全一致，不能一次返回多级提示；
- 三级提示必须关联具体 `solution_step_key`。

这些 Schema 约束与运行时提示策略共同生效。即使数据库存在第四级提示，服务端仍需检查学生尝试次数和会话提示等级。

## 5. Provider 转换责任

具体 Provider 必须按以下顺序处理：

1. 从后端召回短候选，形成内部 `RetrievedKnowledge`；
2. 丢弃无来源、状态不允许、评估集或权限不匹配的候选；
3. 按查询用途解析为结构化对象，不能把候选正文复制到摘要字段冒充结构化；
4. 合并重复概念、公式、题型结构和引用；
5. 执行当前提示等级的披露过滤；
6. 按相关度和教学价值重排；
7. 在数量及字符预算内构建 `RetrievedTeachingContext`；
8. 调用 `to_agent_context()` 后才能写入 Agent Prompt。

Provider 内部诊断只能写入类型固定的 `RetrievalDiagnostics`：延迟、索引版本、候选数、选中数和是否裁剪。不得使用任意字典把原始切片或数据库对象旁路传给 Agent。

## 6. 失败与审计

- 结构化失败：丢弃该候选，并在 `limitations` 记录简短原因；
- 全部候选被丢弃：返回 `no_results` 或 `degraded`，不能回退为原文透传；
- 字符预算超限：重新裁剪，不能依赖字符串截断破坏公式或引用；
- 选中数量必须与结构化对象总数一致；
- Agent 运行记录保存引用 ID、上下文 Schema 版本和索引版本，不保存不必要的候选原文。

## 7. 当前接入状态

领域 Schema、Qdrant Provider 和混合检索 Provider 已完成。默认 Provider 仍是 `DisabledKnowledgeRetriever`；启用 Provider 后，教学 Orchestrator 通过确定性按需策略发起检索，并在每轮限制为最多一次。所有检索 Provider 必须直接实现本契约，不能恢复扁平 `items[].content` 接口。

## 8. 用户可见来源

检索内容实际进入题意、解法或提示上下文后，Orchestrator 从结构化对象的 `citation` 生成 `TutorReply.sources`。每条用户可见来源保留：

- `source_reference_id`、`document_id` 与可选 `chunk_id`；
- 标题、文档版本、URL 与章节或页码定位；
- 该来源在本轮支持的内容类型，例如概念、定理公式、例题结构、完整例题、易错分析或提示依据。

同一文档切片在一轮回答中只展示一次，支持类型合并，最多展示八条。无检索结果、被披露规则丢弃的候选以及没有进入 Agent 上下文的原始候选，不能出现在 `TutorReply.sources`。版本缺失时客户端明确显示“版本未标注”，不能猜测版本。
