# Alembic migrations

Run migration commands from the `math-tutor-agent` directory. The connection is loaded from `.env` through `app.core.config.settings`.

Current baseline and head:

```text
20261031_0035_current_schema_baseline.py
revision = 20261031_0035
down_revision = None
```

The pre-release history was squashed into this one baseline. Existing development databases already stamped at `20261031_0035` do not rerun it. New empty databases use:

```bash
alembic upgrade head
```

After the first shared or production deployment, freeze this baseline and create one new revision for every schema change.

See [MySQL 数据库迁移流程](../docs/module/运行基础设施模块/MIGRATIONS.md) for the full workflow and safety rules.
