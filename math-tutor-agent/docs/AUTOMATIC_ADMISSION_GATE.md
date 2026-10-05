# 规则化自动准入门

## 1. 目标

`RuleBasedAdmissionGate` 在候选题完成各项检查后，根据数据库中的最新证据自动选择：

- `approved`：全部准入规则通过；
- `revision_required`：存在可修复失败且仍有修订次数；
- `quarantined`：存在高风险失败，或修订次数已经用尽；
- 保持 `validating`：证据缺失、未运行或无法形成结论。

调用方不能给准入门传入期望的目标状态。目标状态完全由固定规则生成，模型输出不能直接批准题目。

## 2. 同一题解证据闭包

一题可能有多份 `KnowledgeSolution`。准入门先选择一份来自隔离解题 Agent 的题解，再只读取与该题解一致的证据：

- `solution_independence`；
- `symbolic_verification`；
- `numeric_verification`；
- `constraint_verification`；
- `duplicate_detection`；
- `pedagogical_review`。

题目级证据单独读取：

- `condition_completeness`；
- `evaluation_leakage_detection`；
- `source_rights_clearance`。

不同题解的符号验证、数值验证和 AI 复核不能拼成一次通过结果。所有内容相关证据必须绑定当前题目内容哈希；题解相关证据还必须绑定所选题解内容哈希。

## 3. 确定性规则优先级

以下证据按确定性证据处理：

- `solution_independence`；
- `symbolic_verification`；
- `numeric_verification`；
- `constraint_verification`；
- `duplicate_detection`；
- `evaluation_leakage_detection`；
- `source_rights_clearance`。

规则按下列顺序执行：

1. 查找确定性失败；
2. 决定修订或隔离；
3. 再检查其他阻断失败和结构完整性；
4. 再检查证据缺失或结果不确定；
5. 最后检查完整验证题解和全部通过条件。

即使最新 `pedagogical_review=passed`，只要任何确定性证据失败，准入结论仍然只能是修订或隔离。决策证据会记录 `ignored_model_pass=true`，保留模型意见被规则拒绝的审计事实。

## 4. 修订与隔离策略

### 直接隔离

以下失败不在当前题目版本上自动修补，直接进入 `quarantined`：

- 与已有题目重复；
- 命中隔离评估集；
- 来源权利未通过；
- 证明题缺少形式化证明器或可追溯的合格人工完整复核；
- 开放题缺少穷尽式评分验证或可追溯的合格人工完整复核。

后两类题解即使模型结构复核暂时通过，也只能保留 `partial` 验证状态。覆盖限制来自验证能力边界，不进入自动修订。完整规则见 [证明题与开放题验证覆盖限制](./VERIFICATION_SCOPE_POLICY.md)。

### 有限修订

下列问题在仍有修订次数时进入 `revision_required`：

- 独立解题隔离失败；
- 符号验证失败；
- 数值验证失败；
- 定义域或边界条件失败；
- 条件完整性或教学复核失败；
- 题目结构字段不完整；
- 没有达到完整覆盖的题解。

达到 `KNOWLEDGE_PROBLEM_MAX_REVISION_ATTEMPTS` 后，同类失败进入 `quarantined`。该配置只允许 1 或 2，自动流程还有不可提高的两次硬上限。状态机仍负责实际增加修订次数，准入门不能绕过上限。每次修订创建新的候选题版本并重跑全部校验，具体见 [候选题有限自动修订](./CANDIDATE_REVISION.md)。

### 等待

证据缺失、`not_run` 或 `inconclusive` 时，准入门写入 `admission_decision=inconclusive`，题目保持 `validating`。等待状态不消耗修订次数。

## 5. 批准条件

只有同时满足以下条件才生成 `approved`：

1. 题目结构完整；
2. 同一题解达到 `verification_status=verified` 和完整步骤覆盖；
3. 九类必需证据的最新有效记录全部为 `passed`；
4. Verifier 和模型证据具有正确的版本引用；
5. 不存在其他最新阻断失败；
6. 题目处于 `validating`；
7. 生产索引尚未激活。

最终仍由 `ProblemContentStateMachine` 再检查一次批准条件。规则门负责选择结论，状态机负责验证和执行状态转换，形成双层约束。

## 6. 决策证据

每次评估都追加或幂等复用：

```text
evidence_type = admission_decision
producer_type = system
is_blocking = true
```

状态映射：

| 决策 | Evidence 状态 |
|---|---|
| `approve` | `passed` |
| `revise` | `failed` |
| `quarantine` | `failed` |
| `wait` | `inconclusive` |

载荷记录题目状态版本、所选题解、失败类型、缺失证据、来源证据 ID、目标状态、修订上限和“模型不可覆盖”策略。

## 7. 事务与并发

`AdmissionGateRepository.evaluate_and_persist()` 应在调用方事务中执行。它会：

1. 锁定题目、生成批次、题解和证据；
2. 校验调用方提供的 `expected_status_version`；
3. 选择同一题解的最新有效证据；
4. 运行纯规则决策器；
5. 写入 `admission_decision`；
6. 调用状态机；
7. 写入 `problem_status_transitions`；
8. 重新统计批次的批准数和隔离数。

状态版本不一致时拒绝执行，不覆盖并发任务刚完成的状态变化。

## 8. 调用示例

```python
with session.begin():
    result = repository.evaluate_and_persist(
        session,
        problem_id=problem_id,
        expected_status_version=status_version,
        actor_id="admission-worker",
    )
```

`wait` 决策的 `transition` 为 `None`。其他决策会返回状态机结果和更新后的题目状态版本。
