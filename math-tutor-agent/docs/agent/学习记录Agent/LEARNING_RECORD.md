# 学习记录 Agent

## 1. 职责

`LearningRecordAgent` 在辅导会话达到完成条件后，将真实学习过程整理成结构化 `LearningRecord`。它负责沉淀事实，不负责重新解题，也不根据一次对话给学生生成固定能力标签。

## 2. 输入

- 已完成的 `TutoringSession`；
- 已校验的 `SolutionPlan`；
- 学生实际消息和有效尝试次数；
- 本次会话使用过的提示等级；
- 会话关联的知识点和题目来源。

## 3. 输出

学习记录包括：

- 题目和最终会话状态；
- 本轮可观察的错因或卡点；
- 学生已经成立的步骤和关键突破；
- 有效尝试次数；
- 使用过的最高提示等级；
- 关联知识点及后续复习建议。

## 4. 触发条件

只有在会话出现明确完成事件后才生成学习记录。普通提示轮次不会反复创建完成记录。Harness 保存会话时一并持久化该 artifact，后续由学习历史、间隔复习和家长报告服务使用。

## 5. 边界

1. 只记录会话中真实出现的行为和证据。
2. 不把模型推测写成学生事实。
3. 不生成能力、性格或学习习惯等固定标签。
4. 家长报告必须继续经过授权和样本范围过滤。
5. 学生数据导出或删除时，学习记录服从同一数据归属和隐私流程。

## 6. 相关文档

- [间隔复习与复习任务](../../module/学习记录与复习模块/SPACED_REVIEW.md)
- [家长报告证据与样本范围](../../module/学习记录与复习模块/PARENT_REPORT_EVIDENCE.md)
- [学生数据导出、删除与家长授权撤销](../../module/学生数据与隐私模块/STUDENT_DATA_PRIVACY.md)
- [Agent 协作架构图](../agent协作架构.md)

## 7. 相关代码与目录

- [学习记录 Agent 实现](../../../app/agents/learning_record.py)
- [学习记录与辅导会话领域对象](../../../app/domain/schemas.py)
- [学习记录数据库模型](../../../app/models/learning.py)
- [学习记录持久化 Repository](../../../app/repositories/mysql_sessions.py)
- [学习记录生成编排](../../../app/agents/tutoring_team.py)
- [学习记录查询与复习任务服务](../../../app/services/tutoring.py)
- [学习记录 HTTP API](../../../app/api/routes/tutoring.py)
- [数据库模型目录](../../../app/models/)

