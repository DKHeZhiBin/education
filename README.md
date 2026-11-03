# 数知伙伴

面向中学生的多 Agent 数学辅导产品。学生提交题目后，系统依次完成题意确认、解题分析、独立校验、卡点诊断与分级提示，并在学习完成后形成错题记录。

## 项目组成

- 根目录：React + TypeScript 前端。
- `math-tutor-agent/`：Harness 驱动的 FastAPI 多 Agent 服务，并提供独立 CLI 入口。
- `docs/REQUIREMENTS_ANALYSIS.md`：产品目标、题库定位、核心需求与首版验收标准。
- `docs/TECHNICAL_DESIGN.md`：前端技术方案。
- `math-tutor-agent/docs/README.md`：后端、Agent、题库、RAG 与评估文档总入口。
- `math-tutor-agent/docs/01-architecture/architecture.md`：后端运行架构。
- `math-tutor-agent/docs/01-architecture/SYSTEM_DESIGN.md`：Agent 职责与协作流程。
- `math-tutor-agent/docs/01-architecture/HARNESS.md`：Harness 生命周期、预算、trace 和调用方式。
- `math-tutor-agent/docs/06-curriculum/CURRICULUM_CATALOG.md`：知识点、能力点与先修关系目录。
- `math-tutor-agent/docs/04-question-bank/GENERATION_AUDIT.md`：AI 题库生成版本与准入证据设计。
- `math-tutor-agent/docs/04-question-bank/PROBLEM_LIFECYCLE.md`：题目准入、修订、索引和退役状态机。
- `math-tutor-agent/docs/04-question-bank/KNOWLEDGE_ADMIN.md`：题库管理查询、状态持久化与并发规则。
- `math-tutor-agent/docs/04-question-bank/TRUSTED_SEED_IMPORT.md`：首批可信母题来源、验证与导入流程。
- `math-tutor-agent/docs/02-platform/LLM_PROVIDERS.md`：DeepSeek、Gemini 配置、会话模型选择和联调方式。

## 本地启动

首次使用先按 `math-tutor-agent/docs/02-platform/LOCAL_SERVICES.md` 准备本地运行时与 `.env`。日常开发只需在仓库根目录执行：

```bash
./math-tutor-agent/scripts/dev-stack start
```

该命令按 MySQL、Redis、Qdrant、Embedding、数据库迁移、API、前端的顺序启动并等待就绪。管理命令：

```bash
./math-tutor-agent/scripts/dev-stack check
./math-tutor-agent/scripts/dev-stack status
./math-tutor-agent/scripts/dev-stack logs
./math-tutor-agent/scripts/dev-stack stop
```

打开 `http://localhost:5173`。默认服务地址是 `http://localhost:8000/v1`，可通过根目录 `.env` 中的 `VITE_AGENT_API_URL` 修改。

不配置模型时，演示题 `3(x − 2) = 2x + 5` 可以走完整流程；其他题目会安全降级。配置 DeepSeek 或 Gemini 密钥后，学生可以在开始学习时选择模型，选择结果在整个会话中保持一致。文字版不依赖腾讯云。
