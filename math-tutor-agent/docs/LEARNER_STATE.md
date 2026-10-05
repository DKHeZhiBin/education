# 基于本轮证据的 LearnerState

## 1. 定位

`LearnerState 2.0` 是学生当前一条消息的可观察状态快照，用于选择下一条提示。它不表示学生的长期能力、性格、学习习惯或固定水平。

每一轮都会生成新的 `learner_state` artifact。新状态不会把上一轮的“可能误区”直接复制为事实；需要跨轮汇总时，应由后续独立的学习记录策略根据多轮证据处理。

## 2. 输入边界

诊断 Agent 只接收：

- 学生当前消息；
- 最新 `VerificationReport` 的通过状态和覆盖范围；
- 校验通过时的 `SolutionPlan`。

候选解法未通过校验时，`solution_context` 为空。系统不能使用尚未确认的答案判断学生正误。

## 3. 数据结构

```json
{
  "evidence_scope": "current_turn",
  "observed_work": "3(x-2)=3x-6",
  "attempt_kind": "partial_work",
  "has_meaningful_attempt": true,
  "evidence": [
    {
      "id": "e1",
      "quote": "3(x-2)=3x-6",
      "observation": "学生写出了一个可检查的展开结果",
      "supports": "attempt"
    }
  ],
  "mastered_points": [
    {
      "description": "本轮写出了与已校验解法一致的中间结果",
      "evidence_ids": ["e_verified_match"]
    }
  ],
  "misconception_hypotheses": [],
  "uncertainties": ["还无法判断后续移项是否理解"],
  "possible_misconception": "需要追问",
  "next_hint_level": 1,
  "follow_up_question": "展开后，你准备先处理哪一边的未知数项？",
  "confidence": 0.72
}
```

### 字段规则

| 字段 | 规则 |
| --- | --- |
| `evidence_scope` | 固定为 `current_turn` |
| `observed_work` | 服务端直接取本轮学生消息，模型不能改写 |
| `attempt_kind` | 求助、局部作答、最终答案、证明论证、提问或其他 |
| `has_meaningful_attempt` | 是否包含可检查的数学表达、操作或推理 |
| `evidence[]` | 必须引用学生消息中真实存在的短句 |
| `mastered_points[]` | 只描述本轮证据支持的正确点，每项关联证据 ID |
| `misconception_hypotheses[]` | 具体数学误区假设，每项关联证据 ID 和置信度 |
| `uncertainties[]` | 当前消息仍不能判断的内容 |
| `possible_misconception` | 兼容字段，取第一条误区假设；没有时为“需要追问” |
| `next_hint_level` | 只能为 1、2、3；第四级由服务端展示策略决定 |
| `follow_up_question` | 一个能够区分当前假设的问题 |

## 4. 证据约束

模型给出的 `evidence.quote` 必须能在规范化后的当前学生消息中找到，否则整条证据丢弃。

掌握点与误区假设必须满足：

1. `evidence_ids` 非空；
2. ID 指向保留下来的本轮证据；
3. 证据类型能够支持对应判断；
4. 描述中不含固定能力或人格标签。

没有合格证据时，系统保留不确定性并提出追问，不生成掌握或误区结论。

## 5. 正确答案的解释边界

学生答案与已校验答案一致时，只能生成：

> 本轮给出的结果与已校验答案一致；这只确认结果，不单独证明方法已经掌握。

如果学生写出的中间结果与已校验步骤一致，可以记录“本轮写出了正确中间结果”。仍不能由一次结果推出“已经掌握整个知识点”。

## 6. 禁止固定标签

下列表述会被服务端过滤：

- 能力差、能力弱、基础差；
- 数学不好、不擅长数学；
- 笨、没天赋；
- 粗心、不认真、懒；
- 聪明、天赋好等缺少本轮证据的正向固定标签。

系统应描述具体行为，例如“本轮展开时漏乘了常数项”，并保留为待确认的数学误区。不能写“学生很粗心”。

## 7. 有效尝试计数

`TutoringSession.attempts` 只在 `has_meaningful_attempt=true` 时增加。单纯请求提示、说不知道或直接索要答案不会增加次数。

当前可观察的有效证据包括：

- 数字、等号或数学运算符组成的表达式；
- 设元、代入、展开、移项等具体操作；
- “因为……所以……”形式的推理；
- 明确的证明论证；
- 足够完整且不是纯求助的步骤描述。

该计数参与第四级完整讲解门槛，规则见 `docs/HINT_STRATEGY.md`。

## 8. 降级规则

- 模型不可用：服务端仍生成本轮证据、作答类型和不确定性；
- 没有有效尝试：置信度不高于 `0.45`；
- 可能误区单项置信度不高于 `0.80`；
- 整体状态置信度不高于 `0.85`；
- 解法未校验：明确记录无法判断正误，不生成与标准答案比较的掌握点。
