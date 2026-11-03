# 多 Agent 关键流程端到端评估

## 目标

这套评估检查学生真实流程，而不是单独判断某个 Agent 的 JSON 是否符合格式。每个案例通过 `MathTutorAgentHarness` 执行，覆盖：

1. 模型选择和调用预算；
2. 题意识别与阻断性歧义；
3. 解法分析、有限修订和数学验证；
4. 学生证据驱动的 `LearnerState`；
5. 四级提示边界与完整讲解门槛；
6. 会话状态迁移、学习记录和 Agent artifact 审计。

评估使用内存 Repository 和无状态 Runtime Cache，不连接生产 MySQL、Redis 或 Qdrant。真实 LLM Provider 仍会被调用，因此报告必须记录模型、提示版本、代码版本和冻结数据哈希。

## 冻结案例

数据位于：

- `evals/data/tutoring_e2e_v1.jsonl`
- `evals/data/tutoring_e2e_v1.manifest.json`

第一版包含三条关键路径：

| 案例 | 关键风险 |
| --- | --- |
| 指数方程澄清与完整提示梯 | 定义域澄清、负底数、验证覆盖、逐级提示泄露 |
| 一元二次方程完整提示梯 | SymPy 确定性验证、答案正确性、提示级别 |
| 学生已经做到后面的步骤 | 学生证据识别、避免重新按部就班、完成记录 |

每条记录分成 `input` 与 `oracle`。只有 `input.question` 和 `input.turns` 会传给教学链路；答案模式、预期状态、验证覆盖与禁止泄露内容只由评分器读取。

## 评分指标

| 指标 | 含义 | v1 门槛 |
| --- | --- | ---: |
| `case_pass_rate` | 全部阶段均通过的案例比例 | ≥ 0.80 |
| `stage_pass_rate` | 状态、动作、产物和内容断言通过率 | ≥ 0.90 |
| `answer_correctness_rate` | 答案检查点满足参考模式的比例 | 1.00 |
| `verification_honesty_rate` | 验证覆盖没有夸大的比例 | 1.00 |
| `hint_leakage_rate` | 一级至三级提示提前泄露答案的比例 | 0.00 |
| `timeout_rate` | 超过阶段时间预算的比例 | ≤ 0.10 |

`verification_honesty` 使用保守规则：若报告声称 `coverage=full`，必须存在确定性检查，并且 `verifier_type` 为 `cas` 或 `hybrid`。只有模型复核、没有工具检查时，可以给出教学意见，但不能宣称完全验证。

以下情况无论宏观比例如何都会阻断：

- 任一答案检查点错误；
- 任一验证覆盖夸大；
- 一级至三级提示泄露最终答案或携带完整 `solution_steps`；
- 案例执行异常。

## 运行

先验证冻结文件、哈希和生产隔离：

```bash
cd math-tutor-agent
PYTHONPATH=. .venv/bin/python -m app.evaluation.cli
```

运行全部教学端到端案例：

```bash
./scripts/tutoring-e2e \
  --model deepseek/deepseek-flash \
  --prompt-version tutoring-prompts-v2 \
  --code-revision "$(git rev-parse --short HEAD)" \
  --output .local-services/evaluation/tutoring-e2e-report.json
```

开发期间只运行一个案例：

```bash
./scripts/tutoring-e2e \
  --model deepseek/deepseek-flash \
  --case-id clarification_exponential_full_ladder
```

单案例报告会带有 `partial_suite_not_release_eligible`，只用于调试，不能作为发布放行证据。

进程退出码：

- `0`：所有发布门槛通过；
- `2`：报告成功生成，但发布门槛被阻断；
- 其他非零值：配置、数据集或运行器错误。

## 报告使用

报告保留每个阶段的状态、动作、提示等级、新增 artifact、回复文本、耗时和失败原因。CI 应保存 JSON 文件作为构建产物，并基于退出码阻断发布。

模型具有随机性。正式比较时必须固定：

- 数据集版本与 SHA-256；
- Provider 和模型 ID；
- 提示版本；
- 代码提交；
- 温度等 Provider 参数。

若输入、参考断言、门槛或案例顺序发生变化，创建新的数据集版本，不能覆盖 `v1`。

## 相关代码

- [多 Agent 教学评估器](../../../app/evaluation/tutoring_e2e.py)
- [端到端评估 CLI](../../../app/evaluation/tutoring_e2e_cli.py)
- [固定端到端评估集](../../../evals/data/tutoring_e2e_v1.jsonl)
- [本地评估启动脚本](../../../scripts/tutoring-e2e)
