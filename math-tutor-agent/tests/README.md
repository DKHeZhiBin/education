# 自动化测试

测试覆盖：

- 题目内容与生成批次领域状态迁移；
- MySQL `MySQLSessionRepository` 保存、查询、列表、归属保护和乐观锁；
- Redis `client_turn_id` 幂等结果、TTL、损坏结果处理和会话锁竞争。
- 相似题 S2 结构变化门、独立复核质量选择和三候选并行编排。

## 执行

纯领域测试不需要外部服务：

```bash
PYTHONPATH=. .venv/bin/python -m unittest tests.test_domain_state_transitions -v
```

执行完整核心套件：

```bash
RUN_MYSQL_INTEGRATION_TESTS=1 \
RUN_REDIS_INTEGRATION_TESTS=1 \
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
```

默认使用 `.env` 中的本地 MySQL 和 Redis。CI 或独立测试环境应设置：

```dotenv
MYSQL_TEST_DATABASE_URL=mysql+pymysql://user:password@127.0.0.1:3306/math_tutor_test?charset=utf8mb4
REDIS_TEST_URL=redis://127.0.0.1:6379/15
```

MySQL 测试使用随机用户和会话 ID，并在每个测试后清理。Redis 测试使用随机前缀，并在每个测试后删除该前缀下的键。未设置对应 `RUN_*` 开关时，集成测试明确显示为 skipped，不会误连开发或生产服务。
