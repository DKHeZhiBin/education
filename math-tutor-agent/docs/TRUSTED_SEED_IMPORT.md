# 首批可信母题导入

## 1. 导入范围

首批数据只覆盖“初中一元二次方程”，共 12 道母题。来源为 Portland Community College 的 **Open Resources for Community College Algebra, Edition 2**，具体定位为 `Section 7.2, Exercises 7.2.3` 的第 11、13、15、17、19、21、23、25、27、31、33、35 题。

选择这些题的原因：

- 官方 ORCCA 页面将教材内容声明为 CC BY 4.0；
- 第 2 版练习页和奇数题答案页公开可访问；
- 官方说明第 2 版公开奇数题答案，因此没有使用偶数题；
- 题目不依赖图片、外部视频、WeBWorK 或教师登录资源；
- 每道题都能在实数域由 SymPy 得到有限完整解集并精确代回；
- 内容覆盖求根公式、判别式、无实根、直接开平方法和因式分解法。

数据文件：

```text
app/problem_bank/data/trusted_quadratic_mothers.v1.json
```

许可证核验记录：

```text
rag/sources/evidence/orcca_algebra.json
```

## 2. 数据边界

保存的来源题干是公开练习中的简短方程题。中文题干属于本项目改写，数学表达式不变，并保存原英文题干、精确章节定位、来源 URL、许可证、署名文本和修改说明。

题解不复制答案页的解释。导入器仅从题目方程出发，使用本项目的安全 SymPy 工具独立求解、检查标准形式、确认二次次数并逐根代回。这样可以区分“题目来自开放教材”和“题解由项目确定性生成”两条来源链。

## 3. 写入对象

一次导入会幂等创建或复用：

1. `SourceReference`；
2. 一个固定版本的 `KnowledgeDocument`；
3. 每道题对应的 `DocumentChunk`；
4. 一个 `GenerationBatch`，用途为 `trusted_source_import`；
5. 一个 `VerifierVersion`；
6. 12 个 `KnowledgeProblem`；
7. 12 个经过完整程序验证的 `KnowledgeSolution`；
8. 每题九类 `AdmissionEvidence`。

题目初始状态为 `candidate`，内容审核状态为 `unreviewed`。题解可以标记为 `verified`，因为这个字段只表达数学工具覆盖；它不会让题目自动进入 `approved`。

`pedagogical_review` 证据初始为 `not_run` 且具有阻断属性。因此在独立 AI 教学复核完成前，状态机不会批准这些母题。

## 4. 导入前检查

导入器执行：

- 来源必须存在于允许清单；
- 许可状态必须允许内容导入；
- 数据许可证、主页、具体练习页、署名文本和本地许可证证据必须与允许清单一致；
- 规范方程在数据包内唯一；
- 原方程与标准形式的实数解集一致；
- 标准形式必须是二次多项式且二次项系数非零；
- SymPy 解集必须与数据包预期答案一致；
- 每个返回根必须精确代回成立；
- 题干、中文改写和规范方程不能命中冻结评估集；
- 所有知识点代码必须已经由课程目录导入；
- MySQL 中不能存在其他来源的同内容哈希题目。

## 5. 执行方式

先升级数据库并导入课程目录：

```bash
alembic upgrade head
math-tutor-catalog
```

只做离线校验，不连接 MySQL：

```bash
math-tutor-problem-bank --validate-only
```

确认校验通过后执行事务导入：

```bash
math-tutor-problem-bank
```

重复执行不会重复创建题目、题解或相同证据，也不会把已经批准、索引或退役的内容降级回候选状态。

## 6. 许可履约

对外展示或分发这些题目时，需要显示数据文件中的 ORCCA 署名文本，并保证数学内容可读且至少存在一种 Web 可访问形式。PCC/ORCCA 名称和标志不能作为产品品牌使用，封面、外部视频、WeBWorK 包和未公开偶数题答案不在本次导入范围。
