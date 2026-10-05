# Homework Companion 参考映射

本项目参考了 ClawHub 上 [AI 伴学助手](https://hub.openclaw.ai/wukongmazi/skills/homework-companion) 的公开 Skill 及其引用文件。原 Skill 页面标注 MIT-0 许可证。项目没有直接依赖其腾讯云脚本，而是将教学思想转化为独立的产品架构。

| 原 Skill 内容 | 本项目实现 |
| --- | --- |
| 复述题意、条件缺失时追问 | `ProblemUnderstandingAgent` 与 `ProblemSpec` |
| 请学生先尝试、定位卡点 | `LearnerDiagnosisAgent` |
| 分级提示、逐步确认 | `HintTeachingAgent` 与 1—3 级提示状态 |
| 完成后总结标准解法 | 经校验的 `SolutionPlan` 及完成页 |
| 儿童适宜语言和隐私保护 | `app/prompts/policies.py` 的公共安全约束 |
| 错题本字段 | `LearningRecord` 领域模型与学习记录接口 |
| 家长报告只用真实数据、建议可执行 | `/v1/tutoring/parent-report` 聚合接口 |
| OCR / ASR / TTS | 保留为可选 Provider 边界，首版未绑定腾讯云 |

## 产品化调整

- 原 Skill 是一个指令和脚本集合；本项目用服务端状态机控制 Agent 顺序、重试和数据持久化边界。
- 默认先按方向、关键关系和局部步骤引导。学生明确要求完整讲解，并且已有有效尝试或走到第三级时，可以获得经过校验的分步解法。
- 解题 Agent 的结果必须经过独立校验 Agent；校验失败时不会向学生声称答案可靠。
- 第一版只保存完成学习所需的数据，不主动收集姓名、学校、住址或电话。
