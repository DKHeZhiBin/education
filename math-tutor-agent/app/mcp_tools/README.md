# Math Tutor MCP Tools

该目录提供数学辅导 Harness 会用到的确定性工具。MCP Server 使用 stdio 作为默认传输，适合由 OpenClaw、IDE 或其他 MCP Host 作为子进程启动。

## 工具

| Tool | 用途 | 主要调用方 |
| --- | --- | --- |
| `simplify_math_expression` | 安全化简代数表达式 | 解题分析 Agent、校验 Agent |
| `solve_math_equation` | 求一元实数方程并复核有限解 | 解题分析 Agent、校验 Agent |
| `verify_math_candidate` | 把候选答案代回原方程 | 校验 Agent |
| `compare_solution_steps` | 判断前后两个步骤是否等价 | 校验 Agent、学情诊断 Agent |
| `create_similar_linear_problem` | 生成结果已知的相似练习题 | 练习生成流程 |
| `schedule_question_review` | 计算下一次错题复习日期 | 学习记录 Agent |

## 安全边界

- 数学表达式使用 Python AST 白名单转换成 SymPy 对象，不调用 `eval`、`sympify` 或任意函数。
- 拒绝函数调用、属性访问、下标、非数字常量、超长表达式、过深 AST 和过大指数。
- 工具只返回计算证据，不决定何时向学生展示完整答案。
- 当前 MCP Server 不直接读写 MySQL。学习记录写入仍由 Harness 和 Repository 负责，避免模型绕过业务权限修改数据。

## 启动

安装项目依赖后：

```bash
math-tutor-mcp
```

也可由 MCP CLI 加载：

```bash
mcp run app/mcp_tools/server.py
```

默认使用 stdio。部署为 Streamable HTTP 时，应单独配置认证、允许的 Host、请求大小和进程管理，不与公开的学生 API 共用未授权入口。

## Harness 集成

`SolutionVerificationAgent` 在进程内直接复用本目录的安全工具函数，完成一元实方程独立求解、推荐步骤等价比较、候选答案代回和解集完整性检查。这样与 MCP Server 共用同一套实现和白名单，同时避免内部校验产生额外传输开销。校验顺序、报告对象和当前覆盖边界见 `docs/SOLUTION_VERIFICATION.md`。
