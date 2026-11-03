# 数知内容管理台

独立的知识库管理前端，默认运行在 `http://127.0.0.1:5174`，复用 Math Tutor API。

## 本地启动

推荐从仓库根目录使用统一启动命令，管理端会作为 macOS LaunchAgent 常驻运行：

```bash
./math-tutor-agent/scripts/dev-stack start
```

若其他服务已经运行，只恢复管理端：

```bash
./math-tutor-agent/scripts/dev-stack start-admin
```

也可以临时手动启动：

```bash
cd knowledge-admin
npm install
npm run dev
```

先启动 API 并执行数据库升级与演示账号初始化：

```bash
cd math-tutor-agent
uv run alembic upgrade head
uv run python -m app.demo_accounts_cli
```

开发管理员账号：`admin.demo@example.com`，密码：`MathTutorDemo2026!`。

可复制 `.env.example` 为 `.env` 修改 API 地址。

## 内容维护规范

创建或修改知识点前，请先阅读 [知识目录与知识点命名规范](../math-tutor-agent/docs/06-curriculum/KNOWLEDGE_POINT_NAMING.md)。其中说明了目录编码、知识点编码、父级关系、先修关系、内容键、改名和删除规则。
