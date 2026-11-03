# Agent 文档目录

本目录按照系统中已经实现的 Agent 职责组织文档。子目录使用中文职责名称，索引同时保留 `app/agents/` 中的英文类名，便于从中文文档定位到代码实现。

当前共有 **12 个专职 Agent**。整体协作方式见 [Agent 协作架构图](./agent协作架构.md)。

## 学生在线学习组

| 中文目录 | 代码类名 | 职责 | 主要文档 |
| --- | --- | --- | --- |
| [`题目理解Agent`](./题目理解Agent) | `ProblemUnderstandingAgent` | 提取题型、条件、目标和歧义 | [题目理解 Agent](./题目理解Agent/PROBLEM_UNDERSTANDING.md) |
| [`解题分析Agent`](./解题分析Agent) | `SolutionAnalysisAgent` | 生成多解法、关键突破口和步骤 | [解题分析 Agent](./解题分析Agent/SOLUTION_ANALYSIS.md) |
| [`解答校验Agent`](./解答校验Agent) | `SolutionVerificationAgent` | 独立检查解法及验证覆盖 | [解答校验 Agent](./解答校验Agent/SOLUTION_VERIFICATION.md) |
| [`学情诊断Agent`](./学情诊断Agent) | `LearnerDiagnosisAgent` | 根据本轮作答证据判断当前卡点 | [基于本轮证据的 LearnerState](./学情诊断Agent/LEARNER_STATE.md) |
| [`提示教学Agent`](./提示教学Agent) | `HintTeachingAgent` | 按四级提示策略生成学生回复 | [四级提示教学策略](./提示教学Agent/HINT_STRATEGY.md) |
| [`学习记录Agent`](./学习记录Agent) | `LearningRecordAgent` | 将完成会话整理为结构化学习记录 | [学习记录 Agent](./学习记录Agent/LEARNING_RECORD.md) |
| [`受约束相似题Agent`](./受约束相似题Agent) | `ConstrainedSimilarPracticeAgent` | 以 MPR 表示母题与候选题，生成并复核会话级相似题 | [受约束的相似题生成](./受约束相似题Agent/CONSTRAINED_SIMILAR_PRACTICE.md)、[API](./受约束相似题Agent/API.md)、[MPR 数据模型](./受约束相似题Agent/MPR_DATA_MODEL.md)、[性能优化方案](./受约束相似题Agent/SIMILAR_PRACTICE_PERFORMANCE_OPTIMIZATION.md) |

## 后台题库生产组

| 中文目录 | 代码类名 | 职责 | 主要文档 |
| --- | --- | --- | --- |
| [`变式生成Agent`](./变式生成Agent) | `QuestionVariationAgent` | 从可信母题生成候选变式 | [变式生成 Agent](./变式生成Agent/QUESTION_VARIATION_AGENT.md) |
| [`题意与条件检查Agent`](./题意与条件检查Agent) | `ProblemConditionCheckAgent` | 检查题意、条件、定义域和学段适配 | [题意与条件检查 Agent](./题意与条件检查Agent/PROBLEM_CONDITION_CHECK.md) |
| [`隔离上下文独立解题Agent`](./隔离上下文独立解题Agent) | `IndependentSolvingAgent` | 在隔离上下文中独立解题 | [隔离上下文独立解题 Agent](./隔离上下文独立解题Agent/INDEPENDENT_SOLVING.md) |
| [`独立AI复核Agent`](./独立AI复核Agent) | `IndependentReviewAgent` | 比较答案、工具证据和教学标签 | [独立 AI 复核 Agent](./独立AI复核Agent/INDEPENDENT_AI_REVIEW.md) |
| [`候选题修订Agent`](./候选题修订Agent) | `CandidateRevisionAgent` | 依据明确失败证据生成新候选版本 | [候选题有限自动修订](./候选题修订Agent/CANDIDATE_REVISION.md) |

## 放置规则

1. 只描述单一 Agent 职责、输入、输出、提示词或失败处理的文档，放入对应 Agent 目录。
2. 同时涉及多个 Agent 的业务流程、Harness、状态机、数据库或评估文档，保留在原主题目录，并链接到本目录。
3. 新增 Agent 时，目录名使用简明的中文职责名并保留 `Agent` 后缀，同时在本页登记对应代码类名。
4. Provider、Retriever、Repository、验证器和规则服务不作为 Agent 建目录。

