# deterministic 基线与全栈复现记录

复现时间：2026-10-12（Asia/Shanghai）
基线提交：`d4d65b4 feat: add minimal MCP knowledge search adapter (#5)`
数据性质：ExampleAPI 合成数据；本记录不代表生产准确率或生产部署能力。

## 环境

| 组件 | 版本/状态 |
|---|---|
| 系统 | Windows 10.0.26200.9457 |
| Python | 3.12.10 |
| uv | 0.12.7 |
| Docker Desktop | 29.8.2，Linux Engine |
| Docker Compose | v5.5.1 |
| PostgreSQL 镜像 | `pgvector/pgvector:0.8.6-pg16-trixie` |
| 镜像摘要 | `sha256:c8483555ce48101872f888c1df8a895ff689d6c7c7a5f7ac266475f9dfe89e0b` |

数据库容器：

- `support-pilot-postgres-1`：`localhost:54329`，healthy；
- `support-pilot-postgres-test-1`：`localhost:54330`，healthy。

Docker Hub 在当前网络不可达，因此通过 DaoCloud 镜像代理拉取后按项目原始镜像名打标签。项目 Compose 配置未修改。

## 复现步骤

```powershell
docker compose up -d postgres postgres-test
uv run --no-sync alembic upgrade head
uv run --no-sync alembic check
uv run --no-sync python scripts/seed.py
uv run --no-sync python scripts/ingest_knowledge.py --provider deterministic
uv run --no-sync ruff check .
uv run --no-sync mypy
uv run --no-sync pytest --cov=support_pilot --cov-report=term-missing
```

结果：

- Alembic 从空库升级到 `0006`，`alembic check` 无模型漂移；
- 合成数据播种成功；
- deterministic 知识摄取 10 篇文档、30 个 chunk，Provider 为 `deterministic/hash-lexical-v1`；
- Ruff 通过；Mypy 对 53 个源码文件无问题；
- pytest：`104 passed`，覆盖率 `93%`；
- pytest 仅出现隔离环境无法写入 `.pytest_cache` 的缓存警告，不影响测试结果。

## API 冒烟

服务：`http://127.0.0.1:8000`，Provider 固定为 deterministic。

结果：

| 检查 | 结果 |
|---|---|
| `/api/v1/health/ready` | `{"status":"ready"}` |
| 客户登录 | 成功，返回 Bearer Token |
| `bulk_export` entitlement | `answered`，Alpha 租户该功能未启用 |
| 高风险退款请求 | `refused`，原因：需要人工审批 |
| 同一 `Idempotency-Key` 创建工单 | 两次返回同一公开工单号 `TKT-3D9A7B27D7` |

数据库只读核验：

- 该工单号在 `tickets` 中恰好 1 条；
- `audit_events` 共 8 条，其中 1 条为拒绝类结果；
- `idempotency_records` 共 2 条。

## 后端边界

本记录只证明 deterministic Provider、合成数据和本地 PostgreSQL/pgvector 的后端基线可复现。

尚未在本轮验证：

- Qwen 真实 Provider；
- local BGE Embedding/Reranker；
前端、浏览器 E2E 和完整人工接管演示已在下方补充验证。
- 容器化的 API/frontend 镜像构建与长期运行；
- 生产环境容量、可用性或安全性。
## 前端与浏览器 E2E 补充

前端环境：

- Node.js 22.14.0，npm 10.9.2；
- `npm ci` 安装 245 个依赖；
- ESLint 通过；
- Vitest：4 项通过；
- Vite production build 通过，JS gzip 约 64.70 kB。

Playwright：

- Chromium 端到端：1 passed，耗时约 20 秒；
- 测试自动启动隔离后端 `127.0.0.1:18001`、Vite `127.0.0.1:15174` 和 `support_pilot_test` 数据库；
- 覆盖登录、SSE 引用回答、确认创建工单、支持人员认领并推进到 `in_progress`。

演示脚本：

```powershell
.\scripts\demo.ps1
```

结果：

- knowledge_outcome：`answered`；
- citation_count：`1`；
- ticket_code：`TKT-E544CC0E87`；
- ticket_status：`in_progress`；
- trace_id：`8db8553558bb41bdbb8e77a2ee4f0572`。

本轮补充后仍未验证：Qwen 真实 Provider、local BGE、容器化 API/frontend 镜像构建及生产环境能力。
