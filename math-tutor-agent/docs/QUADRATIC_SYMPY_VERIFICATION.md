# 一元二次方程 SymPy 验证器

## 目标

`QuadraticSympyVerifier` 为 AI 生成的一元二次方程候选题提供确定性证据。它不调用 LLM，不读取变式生成 Agent 的答案，也不直接批准题目。

验证器只处理满足以下条件的内容：

- `problem_type` 为 `quadratic_equation`；
- 题目属于生成批次，状态仍处于准入前；
- 存在且只存在一个规范化方程条件；
- 存在带 `solution_independence` 证据的独立题解；
- 使用已登记并启用的 `quadratic_sympy` 验证器版本。

## 五类校验

### 1. 独立求解

安全解析器先将原方程转为 `left - right`，再提取分子、分母和多项式。分子必须是单变量二次多项式，二次项系数必须非零。SymPy 在实数域求解，结果必须是有限集合。

证据保存规范方程、`a/b/c`、判别式和完整实数解集。

### 2. 候选根代回

从独立题解的 `final_answer` 提取根，将每个根代回原始方程，而非只代入整理后的分子。每次代回同时检查残差为零和原式分母不为零。

安全表达式支持整数、有限小数、分数、幂和 `sqrt`。无法安全解析的答案记为 `inconclusive`，不会被误判为正确。

### 3. 根数量和完整性

比较 SymPy 解集与候选解集，分别记录期望根数、候选根数、漏根和增根。重根按解集中的一个不同实根计算。

空实数解可使用“无实数解”“无解”“空集”或 `∅` 表示。

### 4. 定义域

第一版限定初中一元二次方程的实数域。题目显式声明实数域时直接核对；没有声明时按当前题库范围采用实数域。验证器支持单侧数值边界，例如 `x > 0`、`x <= 3` 和 `x != 1`，并在该定义域内独立求解。若题目要求整数域、自然数域、复数域或无法安全解析的复合区间，验证器返回 `inconclusive`，不能形成准入通过证据。

### 5. 边界条件

边界检查覆盖：

- 二次项系数不为零，防止退化为一次方程；
- 原式分母零点排除，防止通分带入增根；
- SymPy 解和候选解均不能落在原式未定义点。

带参数的不定方程和更复杂的不等式约束暂不在第一版自动通过范围内，应继续停留在准入前状态。

## 题解步骤覆盖

验证器按顺序读取结构化题解步骤：

- 步骤结果是单一方程时，比较与前一方程的实数解集是否相同；
- 步骤结果是最终根集合时，由答案完整性校验覆盖；
- 纯文字推理或无法安全解析的公式列入未覆盖步骤。

状态规则如下：

| 结果 | `KnowledgeSolution.verification_status` | 含义 |
|---|---|---|
| 五类校验通过且全部结构化步骤被覆盖 | `verified` | 可形成完整符号证据 |
| 核心校验未失败，但只有部分步骤被覆盖 | `partial` | 仍需其他验证或复核 |
| 无步骤得到覆盖或核心输入无法解析 | `unverified` | 只在准入证据中保存失败原因 |
| 任一确定性校验失败 | `failed` | 阻断后续自动准入 |

`partial` 和 `unverified` 都不能被视为答案正确的完整证明。

## 持久化与幂等

`QuadraticVerificationRepository` 在运行前构造带题目哈希、题解哈希、状态版本和输入指纹的只读上下文。保存时重新加锁读取对象；内容发生变化就抛出版本冲突，不写入过期结果。

一次验证写入两类阻断证据：

- `symbolic_verification`：求解、代回、根完整性和步骤等价；
- `constraint_verification`：定义域和边界条件。

证据由 `verifier_version_id` 标识实现版本，并用规范 JSON 哈希保证重复执行幂等。验证器只更新题解验证状态，不改变题目的内容状态，也不会创建 `approved` 或 `indexed` 内容。

## 调用顺序

```python
repository = QuadraticVerificationRepository()
loaded = repository.load_verifier_context(
    session,
    problem_id=problem_id,
    solution_id=solution_id,
    verifier_version_id=verifier_version_id,
)

report = QuadraticSympyVerifier().verify(loaded.verification_context)
result = repository.persist_report(session, context=loaded, report=report)
session.commit()
```

调用方应在部署时登记 `verifier_key=quadratic_sympy`、支持题型包含 `quadratic_equation` 的 `VerifierVersion`，并在实现或规则变化时创建新版本，不能覆盖旧版本记录。
