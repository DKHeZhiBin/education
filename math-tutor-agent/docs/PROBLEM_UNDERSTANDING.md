# 题目理解 Agent

## 1. 职责

`ProblemUnderstandingAgent` 只把学生提交的题目整理成结构化 `ProblemSpec`，不计算答案、不生成解题步骤，也不猜测缺失条件。该产物是解题分析和独立校验的共同输入。

题目理解分为两层：

1. 本地规则先识别常见题型、关系式、目标及明显缺失信息，保证没有配置 LLM 时仍能安全工作；
2. LLM 在规则结果基础上补充复杂语义，最终输出仍由 Pydantic 合约清洗和限制。

规则发现的缺图、缺选项、括号不闭合等问题不会被 LLM 结果覆盖。

## 2. ProblemSpec 2.0

| 字段 | 含义 |
| --- | --- |
| `normalized_question` | 保持原意和公式不变的规范题干 |
| `subject` / `grade_band` | 创建会话时声明的学科和学段，模型只能在有依据时细化 |
| `question_type` | 当前最可信的主题型 |
| `question_type_candidates[]` | 候选题型、置信度和题干证据 |
| `known_conditions[]` | 条件内容、类别、来源和置信度 |
| `target` | 求解动作、目标对象、答案形式及来源 |
| `ambiguities[]` | 歧义类别、影响等级、说明和对应澄清问题 |
| `needs_clarification` | 是否存在阻断可靠求解的歧义 |
| `clarification_questions[]` | 按当前识别结果生成的具体问题 |
| `confidence` | 对题目表示完整性和可靠性的综合置信度 |

条件的 `source` 区分原文明确给出的 `explicit` 和可直接安全推出的 `inferred`。下游 Agent 可以使用两者，但必须保留来源，不能把模型猜测写成已知条件。

## 3. 题型范围

当前稳定题型代码包括：

- 算术、代数式、一般方程、方程组、一元一次方程、一元二次方程和不等式；
- 函数、三角、数列、微积分和优化；
- 平面/立体几何、解析几何和证明；
- 组合计数、概率、统计和数论；
- 数学应用题及暂时无法可靠分类的 `unknown`。

候选列表允许复杂题同时保留多个可能类型。主类型用于路由，候选及证据用于后续 Agent 判断是否需要专用工具。

## 4. 歧义处理

歧义分为：

- `blocking`：缺图、缺选项、关键条件缺失、符号指代不清、求解目标缺失或表达式不完整；
- `warning`：存在多种合理解释，但仍可在明确假设下继续分析。

只要存在 `blocking` 歧义，Harness 就进入 `clarifying` 状态，暂停 `SolutionAnalysisAgent` 和 `SolutionVerificationAgent`。学生补充信息后，系统把补充内容并入题干并重新运行题目理解；阻断问题消失后才启动解题链。

## 5. 示例

输入：

```text
解方程 3(x - 2) = 2x + 5
```

核心产物：

```json
{
  "question_type": "linear_equation",
  "known_conditions": [
    {
      "statement": "解方程 3(x - 2) = 2x + 5",
      "kind": "equation",
      "source": "explicit",
      "confidence": 1.0
    }
  ],
  "target": {
    "action": "solve",
    "object": "3(x - 2) = 2x + 5",
    "expected_answer_type": "solution_set",
    "source": "explicit"
  },
  "ambiguities": [],
  "needs_clarification": false
}
```

输入 `如图，求阴影部分面积` 时会产生 `missing_diagram` 阻断歧义，并询问学生上传图片或补充图中的长度和位置关系。
