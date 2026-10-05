# 数值抽样与穷举验证

## 目标

`QuadraticNumericVerifier` 为一元二次方程提供独立于 SymPy 的第二类确定性证据。实现只使用 Python 受限 AST 和 `Decimal`：

- 不导入 SymPy；
- 不读取 `symbolic_verification` 的解集、判别式或结论；
- 不调用 LLM；
- 不直接修改题目状态或准入结果。

验证结果保存为阻断型 `numeric_verification`。后续自动准入门应同时要求符号证据和数值证据通过。

## 数值抽样模式

默认模式适用于实数域一元二次方程。

### 1. 安全解析

验证器通过 Python AST 白名单解析数字、单变量、加减乘除、整数幂和单参数 `sqrt`，不会使用 `eval`。表达式长度、AST 节点数和指数大小均有限制。

### 2. 独立重建系数

分别计算原方程残差函数在 `x=-1、0、1` 的值，并重建：

```text
c = f(0)
a = (f(1) + f(-1)) / 2 - c
b = (f(1) - f(-1)) / 2
```

若 `a` 精确为零，验证失败，说明题目退化或结构与二次方程声明冲突；若 `a` 非零但小于当前数值容差，则返回 `inconclusive`，避免把精度不足误判成确定性错误。

### 3. 固定点抽样

在 `-7、-5、-3、-2、2、3、5、7` 上分别计算原方程残差和重建多项式的值。所有点必须在绝对或相对容差内一致。固定样本使相同输入得到相同证据哈希，便于审计和重放。

任何采样点出现除零或表达式未定义时返回 `inconclusive`。这类题不能自动准入，应交给更适合的验证器。

### 4. 独立计算根

使用 `Decimal` 判别式与求根公式计算不同实根，再与独立题解的候选根进行容差集合比较。该计算不读取 SymPy 结果。

### 5. 数值代回

将候选根直接代入原方程左右两侧，比较残差。代回使用 50 位十进制精度，默认绝对容差为 `1e-20`，相对容差为 `1e-18`。

## 有限整数域穷举模式

当结构化定义域同时声明整数和闭区间，例如 `-10 <= x` 与 `x <= 10`，验证器逐个计算区间中的每个整数：

- 记录每个整数的残差和是否为解；
- 汇总全部整数解；
- 与候选答案比较完整性；
- 再独立执行候选解代回。

默认最多穷举 1001 个点。缺少上下界、区间无效或超过预算时返回 `inconclusive`。

## 状态规则

| 状态 | 条件 | 准入含义 |
|---|---|---|
| `passed` | 所有适用检查通过 | 可作为第二类准入证据 |
| `failed` | 任一确定性检查失败 | 阻断自动准入 |
| `inconclusive` | 无法安全解析、样本点无定义或穷举预算不足 | 证据不足，阻断自动准入 |

数值证据用于交叉验证，不替代符号证明。浮点近似通过不能覆盖 SymPy 的确定性失败；任一验证器失败都应进入修订或隔离。

## 持久化与版本

`NumericVerificationRepository` 要求：

- 候选题仍处于准入前状态；
- 题解来自隔离解题 Agent；
- 最新 `solution_independence` 证据与题目、题解哈希一致；
- 使用启用的 `quadratic_numeric` VerifierVersion。

Repository 在写入前重新锁定题目和题解，并比较内容哈希、状态版本与完整输入指纹。输入发生变化就拒绝写入旧报告。证据 Payload 明确记录 `sympy_result_read=false`，并通过规范 JSON 哈希实现幂等。

## 调用顺序

```python
repository = NumericVerificationRepository()
loaded = repository.load_verifier_context(
    session,
    problem_id=problem_id,
    solution_id=solution_id,
    verifier_version_id=verifier_version_id,
)

report = QuadraticNumericVerifier().verify(loaded.verification_context)
evidence = repository.persist_report(session, context=loaded, report=report)
session.commit()
```

部署时应登记 `verifier_key=quadratic_numeric`、支持题型包含 `quadratic_equation` 的 VerifierVersion。精度、容差、样本点或穷举预算改变时应创建新版本，保留旧证据的可复现性。
