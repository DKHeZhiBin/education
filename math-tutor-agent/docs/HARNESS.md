# Math Tutor Agent Harness

`MathTutorAgentHarness` 是数学辅导系统唯一的 Agent 运行入口。HTTP API、CLI、未来的 OpenClaw Skill 或消息渠道都通过 Harness 发起运行，不直接实例化 Agent、模型 Provider 或 Repository。

## Harness 职责

1. 创建 `run_id`，装配本轮运行上下文。
2. 读取或创建学习会话。
3. 在预算范围内调用 `TeachingOrchestrator`。
4. 收集各 Agent 的 artifact、置信度与耗时，形成 trace。
5. 判断是否进入模型缺失或超时降级状态。
6. 在回复返回前保存完整会话。
7. 向不同入口返回统一的 `HarnessRunResult`。

Harness 不负责具体数学推理，也不包含 HTTP 异常或页面逻辑。专职 Agent 只负责自己的任务；Orchestrator 决定本轮调用顺序；Harness 管理完整运行生命周期。

## 目录

```text
app/harness/
  contracts.py      # 预算、运行结果、trace 和 Harness 异常
  factory.py        # 依赖装配入口
  math_tutor.py     # MathTutorAgentHarness
app/agents/
  tutoring_team.py  # 专职 Agent 与 TeachingOrchestrator
app/providers/      # 模型及后续数学/OCR Provider
app/repositories/   # 会话存储协议、MySQL 实现与旧版 SQLite 适配器
app/api/            # HTTP 适配器
app/cli.py          # CLI 适配器
```

## 运行结果合约

每次 `start_session` 或 `run_turn` 返回 `run_id`、会话快照、学生回复、本轮 trace、总耗时及降级状态。内部 trace 不包含模型的隐藏推理过程，只保存结构化产物和运行元数据。

## 预算

- `HARNESS_MAX_AGENT_CALLS`：单轮最多 Agent 调用次数，默认 8。
- `HARNESS_MAX_DURATION_MS`：单轮软时间预算，默认 60000 毫秒。
- `SOLUTION_MAX_REVISION_ATTEMPTS`：校验失败后的最大自动修订次数，默认 2，范围 0 到 3。

调用次数在运行前检查。时间预算目前是运行后标记的软限制；接入可取消的异步模型 Provider 后，可升级为主动中止。
新题和澄清完成后的最坏调用数按 `4 + 2 × 最大修订次数` 预留。修订流程详见 `docs/SOLUTION_REVISION.md`。

## 调用方式

Python：

```python
from app.harness.factory import build_math_tutor_harness

harness = build_math_tutor_harness()
result = harness.start_session("3(x - 2) = 2x + 5", "数学", "初中")
```

CLI：

```bash
math-tutor-harness "3(x - 2) = 2x + 5" --student-id <student_uuid>
```

HTTP 返回也包含本轮运行元数据。完整会话轨迹可通过 `GET /v1/tutoring/sessions/{session_id}/trace` 查询。
