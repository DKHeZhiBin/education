# 可信母题批量变式生成

## 1. 这项功能是做什么的

这项功能由管理员或后台任务发起：系统从已经确认可靠、来源清楚的母题出发，让 AI 批量生成结构相似但参数、条件、问法或情境不同的候选题。

它解决的是“怎样有控制地扩大题库”，不是“学生每次点击练习时临时随便生成一道题”。生成结果首先只是候选内容，必须继续经过验证与准入流程。

## 2. 为什么单独作为一个子模块

一次批量生成同时涉及：

- 选择可信母题和允许的变化方式；
- 确定生成数量、模型、提示版本和预算；
- 防止网络重试造成重复生成；
- 记录每一道候选题来自哪道母题；
- 支持暂停、恢复、取消和失败重试；
- 把结果交给后续验证与准入模块。

这些规则共同组成一个完整业务能力，因此从“题库生产与治理”总目录中拆出独立子目录维护。

## 3. 负责与不负责的范围

### 本子模块负责

- 根据管理员给出的范围创建生成任务；
- 只从可信母题生成候选变式；
- 保存生成批次、任务输入、预算、进度和逐题结果；
- 保证同一请求可以安全重放；
- 在暂停或失败后从未完成的位置继续；
- 将生成成功的题目保存为 `candidate`。

### 本子模块不负责

- 不把 AI 生成的答案直接作为标准答案；
- 不决定候选题是否正确；
- 不允许生成 Agent 批准自己的输出；
- 不直接写入关键词或 Qdrant 生产索引；
- 不处理学生在线点击“做相似题”的临时生成流程。

候选题的正确性由条件检查、独立解题、数学验证、去重、泄漏检查、独立复核和规则化准入门共同判断。学生在线相似题属于[受约束相似题 Agent](../../../agent/受约束相似题Agent/CONSTRAINED_SIMILAR_PRACTICE.md)。

## 4. 本目录文档

| 文档 | 先回答什么问题 | 适合谁阅读 |
| --- | --- | --- |
| 当前文档 | 这项业务为什么存在、整体怎样运行、怎样调用 | 产品、开发、维护者 |
| [HTTP API](./API.md) | 管理端通过哪些接口创建、查询和控制生成任务 | 前端开发、后端开发、接口调用方 |
| [数据模型](./DATA_MODEL.md) | 生成请求、批次、Job、候选结果、证据和审计事件怎样保存及关联 | 后端开发、数据维护者 |
| [QuestionGenerationJob 合约](./QUESTION_GENERATION_JOB.md) | 一次生成任务的输入、输出、预算和幂等规则是什么 | 后端开发、接口调用方 |
| [生成批次管理](./GENERATION_BATCH_MANAGEMENT.md) | 管理员怎样暂停、恢复、取消、重试和撤回批次内容 | 管理端、后端开发、运维 |

相关但仍保留在其他目录的文档：

- [首批可信母题导入](../TRUSTED_SEED_IMPORT.md)：解释母题怎样获得可信身份；
- [变式生成 Agent](../../../agent/变式生成Agent/QUESTION_VARIATION_AGENT.md)：解释单道候选题如何生成；
- [规则化自动准入门](../AUTOMATIC_ADMISSION_GATE.md)：解释候选题何时能够进入正式题库；
- [题库内容状态机](../PROBLEM_LIFECYCLE.md)：解释 `candidate`、`approved`、`indexed` 等状态。

## 5. 业务目标

批量生成器从已经通过审核的可信母题中生成候选变式题，并完整保存任务输入、模型与提示版本、预算、逐题结果、来源关系、失败原因和批次终态。

生成器只创建 `candidate` 内容。它没有批准权限，也不会把生成模型给出的答案写成标准答案。候选题后续仍需经过条件检查、隔离解题、数学验证、重复检测、独立复核和自动准入门。

## 6. 执行流程

1. 校验幂等键、模型版本、提示版本和预算。
2. 校验全部母题仍为 `approved` 或 `indexed`，且带有可信来源、年级和知识点标签。
3. 创建一条 `generation_batches` 和一条一对一的 `question_generation_jobs` 记录。
4. 按输入顺序加载母题，不向生成 Agent 暴露母题题解。
5. 按候选序号轮询分配母题。例如 3 道母题生成 8 道题时，分配顺序为 `A、B、C、A、B、C、A、B`。
6. 每个候选使用稳定的 `candidate_key` 调用 `QuestionVariationAgent`。
7. 每生成一道题，立即以 `candidate` 状态保存，并在同一事务内更新批次进度。
8. 每个位置都记录为 `candidate_created`、`generation_failed` 或 `skipped`。
9. 全部位置处理完毕，或遇到取消、预算耗尽、Provider 不可用时，写入批次终态和停止原因。

任一候选保存失败只回滚该候选，不会删除同批次已经成功保存的候选。

## 7. 完整记录

生成批次、Job、候选题、准入证据和管理事件的数据对象、字段、关系及约束统一定义在 [DATA_MODEL.md](./DATA_MODEL.md)。

## 8. 状态与恢复

- `pending`：任务已登记，尚未开始。
- `running`：正在逐题生成和保存。
- `paused`：保留已有候选、用量和序号，可以恢复。
- `completed`：全部候选位置成功。
- `partial_failed`：至少一题成功，其他位置失败或跳过。
- `failed`：没有成功保存候选。
- `cancelled`：取消后未处理的位置记为 `skipped`。

执行器会跳过输出中已经存在的序号，因此恢复时只继续未完成位置。管理员恢复操作和执行器启动使用同一 `attempt_count`，不会重复增加执行次数。

## 9. HTTP API

管理员创建、查询和控制生成任务所使用的接口、身份要求及请求示例已经拆分到 [API.md](./API.md)。

## 10. CLI

长批次建议由独立进程执行：

```bash
math-tutor-generate create --file generation-request.json
math-tutor-generate show <job_id>
math-tutor-generate run <job_id>
```

CLI 和 HTTP 共用同一 Service、Repository、幂等规则和事务边界。

## 11. 自动验证流水线

当前大学高数 MVP 创建任务时必须设置 `auto_validate=false`。`quadratic-v1` 只保留为历史回归基线，不能验证大学高数题。待具体高数题型的确定性验证配置与隔离评估集完成后，自动验证会对每一道候选题依次执行：

1. 题意、条件、定义域、解数量与学段检查；
2. 隔离上下文的独立解题；
3. SymPy 符号求解、代回、根数量与约束验证；
4. Decimal 数值抽样或有限域穷举验证；
5. 文本、公式 AST、条件结构与解法结构四层重复检测；
6. 固定评估集泄漏检测；
7. 独立 AI 复核；
8. 规则化准入门决策。

准入门只有在同一内容哈希和同一独立题解上收齐以下最新证据时才允许
`validating → approved`：条件完整性、独立解题、符号验证、数值验证、约束验证、
四层去重、评估集泄漏检测、独立教学复核和来源许可。来源许可只能从具有系统级
`source_rights_clearance=passed` 的可信母题继承，并记录母题证据 ID、许可证、来源 URL
和候选题内容哈希。

批准后系统才会尝试生产索引同步。关键词索引和 Qdrant 都成功激活并写入
`index_sync=passed` 后，状态才会从 `approved` 迁移到 `indexed`。Embedding Provider、
Qdrant 或数据库同步失败时内容保持 `approved`，不会伪造 `indexed` 状态；生产检索层
只读取已经激活的索引记录。

生成预算必须为每题预留最多四次模型调用：生成、条件检查、独立解题和独立复核。
任一确定性证据失败或缺失都会要求修订或隔离，模型复核不能覆盖该结论。

首次部署先登记固定版本：

```bash
math-tutor-generate bootstrap-validation <model-version-id>
```

已有批次可以重新触发验证：

```bash
math-tutor-generate validate <batch-id> --profile quadratic-v1
```

结果逐题列出每个阶段、证据 ID、最终内容状态和错误摘要。完整证据保存在
`admission_evidence`，状态变化保存在 `problem_status_transitions`。

## 12. 当前计量边界

当前 OpenAI-compatible Provider 只返回解析后的 JSON，没有返回响应 usage。因此首版可以可靠累计模型调用次数、候选尝试数和墙钟耗时；输入 token、输出 token 和费用字段暂时保持未采集状态。生产环境在启用 token 或费用硬限额前，需要让 Provider 返回实际 usage，或接入经过校准的保守估算器。

## 相关代码

- [变式生成 Agent](../../../../app/agents/question_variation.py)
- [题意条件检查 Agent](../../../../app/agents/problem_condition_check.py)
- [隔离解题 Agent](../../../../app/agents/independent_solving.py)
- [独立复核 Agent](../../../../app/agents/independent_review.py)
- [候选验证服务](../../../../app/services/candidate_validation.py)
- [题目生成服务](../../../../app/services/question_generation.py)
