# SupportPilot

[![CI](https://github.com/EthanZ-zh/support-pilot/actions/workflows/ci.yml/badge.svg)](https://github.com/EthanZ-zh/support-pilot/actions/workflows/ci.yml)

SupportPilot 是面向虚构 B2B API 平台 `ExampleAPI` 的技术支持与智能工单 Agent。本仓库已完成从确定性业务基线、混合 RAG、受控 Agent、安全闭环到 React 控制台的纵向业务链路。

> 所有租户、用户、事故和工单样例均为合成数据，不代表真实企业或生产效果。

## 当前请求链路

`POST /api/v1/auth/login → Argon2id 校验 → JWT → Bearer 身份 → 租户授权 → PostgreSQL 查询/写入 → 审计`

支持的结构化 intent：

- `entitlement`：查询租户功能权益；
- `quota`：查询最新额度快照并由代码计算剩余额度；
- `incident`：按组件、区域和时间查询匹配事故；
- `ticket_request`：通过 `Idempotency-Key` 幂等创建工单；
- `high_risk`：拒绝退款、权限修改、密钥操作和运维命令等高风险动作。

JWT/RBAC、人工接管 API、状态机、幂等反馈、领域级多轮恢复和 LangGraph 节点级 SSE 进度已经实现。持久化的是会话和每次运行的最终状态与 Trace；跨进程节点级 checkpoint 仍是后续增强项。

知识检索链路：

`POST /api/v1/knowledge/search → metadata filters → keyword/vector recall → RRF → rerank → single/multi-evidence Answerability Gate → citations`

当单个 chunk 都未达到门控阈值时，系统仅会将同文档、同主题、同答案版本的最多 3 个候选聚合重评分，不会降低 Provider 阈值。通过后仍返回抽取式原文和每个 chunk 的独立引用；任一选中证据命中 Prompt Injection 都会整体安全升级。

Agent 链路：

`POST /api/v1/agent/resolve/stream → load conversation → safety preflight → DecisionProvider/resume → risk gate → RAG/read tool/draft/confirm/refusal → progress SSE → AgentConversation + AgentRun + trace`

当前 Agent 使用确定性 Provider 做 CI 和流程回归，并已实现和真实验证百炼 Qwen3.7 Plus 意图分类适配器；知识答案仍是有引用的抽取式结果，不伪装成模型生成结果。7 条真实 Provider 冒烟结果记录在阶段评测报告中，不能视为生产准确率。

## 本地运行

要求：Python 3.11+、[uv](https://docs.astral.sh/uv/) 和正在运行的 Docker Desktop。

```powershell
uv sync --group dev
docker compose up -d postgres
uv run alembic upgrade head
uv run python scripts/seed.py
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run uvicorn support_pilot.main:app --reload
```

首次运行前生成本地 JWT 密钥并保存到 Windows 用户环境（新终端生效）：

```powershell
$jwtBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Fill($jwtBytes)
$jwtSecret = [Convert]::ToHexString($jwtBytes)
[Environment]::SetEnvironmentVariable('SUPPORT_PILOT_JWT_SECRET', $jwtSecret, 'User')
```

检查服务：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/ready
```

使用合成演示账号登录，再查询租户 Alpha 的 `bulk_export` entitlement：

```powershell
$login = Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/login `
  -ContentType 'application/json' `
  -Body (@{
    email = 'alpha.admin@example.com'
    password = 'SupportPilotDemo!2026'
  } | ConvertTo-Json)

$body = @{
  intent = 'entitlement'
  message = '为什么不能使用批量导出？'
  tenant_id = '20000000-0000-0000-0000-000000000001'
  feature_code = 'bulk_export'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/support/resolve `
  -Headers @{ Authorization = "Bearer $($login.access_token)" } `
  -ContentType 'application/json' `
  -Body $body
```

API 文档位于 `http://127.0.0.1:8000/docs`。

启动 React 控制台（另开终端，npm 缓存保留在 D 盘）：

```powershell
Set-Location frontend
$env:npm_config_cache = 'D:\model-cache\support-pilot\npm'
npm ci
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。客户演示账号为 `alpha.admin@example.com`，支持人员账号为 `support.agent@example.com`，两者使用仓库合成数据约定的演示密码 `SupportPilotDemo!2026`。该密码不能用于任何真实环境。

运行可复现业务演示（后端已启动且完成知识摄取）：

```powershell
.\scripts\demo.ps1
```

脚本会验证“带引用知识回答 → 客户确认工单 → 支持人员认领 → 推进处理中”，并输出 ticket code 与 trace id。

Docker Compose 也包含 API 和前端：

```powershell
docker compose build api frontend
docker compose up -d
```

本机 2026-09-10 的镜像构建仍在拉取基础镜像元数据时被 Docker Hub 鉴权端点 TCP 超时阻断；GitHub Actions 的 Linux runner 已成功构建镜像、执行 `docker compose up -d --wait`，并分别验证 API、前端页面及 Nginx 到 API 的 `/api/v1/health/ready` 代理链路。该结果证明仓库当前的 Compose 运行链路可复现，不代表生产部署或长期稳定性验证。

启用 Qwen 时，在被 Git 忽略的 `.env` 中把 `SUPPORT_PILOT_AGENT_PROVIDER` 改为 `qwen`。API Key 推荐保存为 Windows 用户级 `DASHSCOPE_API_KEY`；也支持只写在 `.env` 的 `SUPPORT_PILOT_QWEN_API_KEY`。绝不能把真实 Key 写入 `.env.example`，该文件只是可提交的空模板。共享北京 Base URL 可用于开发；正式部署应改为与 Key 同一业务空间的专属域名。未配置 Key 时 Agent API 会返回 503，不会静默回退或泄露密钥。

真实本地 RAG 使用 BGE 模型，默认缓存到 D 盘：

```powershell
$env:UV_CACHE_DIR = 'D:\model-cache\support-pilot\uv'
$env:HF_HOME = 'D:\model-cache\support-pilot\huggingface'
uv sync --group dev --group rag-local
uv run python scripts/download_rag_models.py
uv run python scripts/ingest_knowledge.py --provider local_bge
uv run python scripts/evaluate_retrieval.py --provider local_bge
```

默认检索评测使用冻结后独立 holdout；原 60 条同源数据仅作 calibration 和回归。完整指标、混淆矩阵与限制见[ RAG 离线评测](./docs/evaluation/stage-3-rag-evaluation.md)。

claim 级引用与忠实度评测使用独立 faithfulness v2 数据集和确定性 verifier：

```powershell
uv run python scripts/evaluate_faithfulness.py
```

完整指标和失败样本见[第九阶段忠实度评测](./docs/evaluation/stage-9-faithfulness-evaluation.md)。

可通过 `SUPPORT_PILOT_MODEL_CACHE_DIR` 覆盖模型目录。真实模型首次下载和 CPU 重排较慢；确定性 Provider 只用于 CI 和流程回归。

## 可观测性与定时维护

设置 `SUPPORT_PILOT_OTEL_ENABLED=true` 后，API 会同时导出 Trace 和 Metrics 到 OTLP HTTP 端点；未启用时埋点为 no-op。本地可用 Compose `observability` profile 启动 Collector 查看信号：

```powershell
docker compose --profile observability up -d otel-collector
docker compose --profile observability logs -f otel-collector
```

Agent、RAG 与历史清理提供 `agent.run`、`agent.resume`、`rag.retrieval`、`agent.retention.prune` 四个 Span 和对应的 counter/histogram 指标，标签只使用有界枚举。当前 Collector 只配置 debug exporter，用于本地验证链路，不接 Jaeger/Prometheus，也不代表生产监控或 SLO。

历史清理通过维护脚本执行，默认 dry-run：

```powershell
.\scripts\run_maintenance.ps1
.\scripts\run_maintenance.ps1 -Execute
```

日志写入被忽略的 `logs/`。完整命令、Span/指标清单与排障见[运维手册](./docs/operations/runbook.md)。

## 浏览器会话与 CSRF

浏览器端不再把令牌存进 `localStorage`：登录后由服务端下发三个 Cookie——`support_pilot_access`、`support_pilot_refresh`（均 HttpOnly）和可被前端读取的 `support_pilot_csrf`。所有写请求（POST/PUT/PATCH/DELETE）必须带 `X-CSRF-Token` 头并与该 Cookie 一致，同时与会话行绑定；不满足返回 403 `csrf_token_invalid` 并写审计。刷新页面时前端先试 `/auth/me`，401 再试一次 `/auth/refresh`，两者都失败才回到登录页。

访问令牌带 `sid` 声明并绑定会话行，所以登出或撤销后立即失效，而不是等令牌过期。refresh 令牌每次使用都会轮换，旧令牌重放返回 401。命令行脚本、集成测试与第三方客户端仍可显式使用 `session_mode="token"` 获取 Bearer 令牌；`scripts/demo.ps1` 即使用该模式。

会话可管理：`GET /api/v1/auth/sessions` 列出当前账号的活跃会话并标出当前会话，`POST /api/v1/auth/sessions/{id}/revoke` 撤销指定会话（撤销他人会话返回 404），`POST /api/v1/auth/logout-all` 一键撤销全部会话。控制台顶栏提供"登出所有设备"。过期的会话行由维护脚本按保留期清理，只删除 `expires_at` 早于 `now - SUPPORT_PILOT_AUTH_SESSION_RETENTION_DAYS` 的记录，活跃会话在判定上不可能被选中。

本地默认 `SUPPORT_PILOT_AUTH_COOKIE_SECURE=false`，通过 HTTPS 部署时必须改为 `true`。当前实现未包含设备指纹、IP 记录、活跃会话数量上限和 OIDC；`SameSite=Lax` 加双提交是纵深防御，不是 CSRF 的形式化证明。

## 工单通知与验证边界

创建工单的数据库事务提交后，系统通过可配置的 `OutboundChannel` 发送通知；通知失败只记录公开工单号，不回滚已经创建的工单，使用同一幂等键重放也不会重复投递。默认 `log` 通道无需外部服务；`smtp` 和 `webhook` 通过 `.env` 中的 `SUPPORT_PILOT_NOTIFICATION_CHANNEL` 切换。

SMTP 密码与 Webhook URL 使用 `SecretStr` 保存；认证 SMTP 强制启用证书和主机名校验，Webhook 强制 HTTPS、显式主机白名单并拒绝非公网 IP 与环境代理。自动化测试只使用 Mock/Fake 外部边界，不代表真实邮件或群机器人已经完成线上投递验证。

当前验证结果为 136 项后端测试通过；14 项前端单元测试和 1 条浏览器业务 E2E 已在本机复跑通过；80 场景 deterministic Agent 评测 80/80；faithfulness v2 的 claim support rate 为 1.000、false answer rate 为 0.000、claim coverage 为 0.8333。Alembic upgrade/check 已通过。浏览器 E2E 使用确定性 Provider、隔离的 `support_pilot_test` 数据库和 `log` 通知通道，不会调用付费模型或外部通知服务。

## 验证

```powershell
docker compose up -d postgres-test
uv run ruff check .
uv run mypy
uv run pytest
uv run alembic check
Set-Location frontend
npm run lint
npm run test
npm run build
$env:PLAYWRIGHT_BROWSERS_PATH = 'C:\Users\刘雨晴\Documents\github\.playwright-browsers'
npx playwright install chromium
npm run test:e2e

# 无法下载 Playwright 自带浏览器时，可改用系统安装的浏览器通道（Chrome/Edge）：
$env:E2E_BROWSER_CHANNEL = 'chrome'
npm run test:e2e
```

集成测试默认连接：

`postgresql+psycopg://support_pilot:support_pilot@localhost:54330/support_pilot_test`

可以通过 `SUPPORT_PILOT_TEST_DATABASE_URL` 覆盖。测试会清空项目表中的数据，因此测试服务使用独立数据库和临时文件系统，不能把该变量指向开发或生产数据库。Playwright 还会校验 `E2E_DATABASE_URL` 的数据库名必须严格等于 `support_pilot_test`，不满足时在迁移前直接终止。

## 文档

- [产品定义](./docs/product/product-definition.md)
- [数据字典](./docs/product/data-dictionary.md)
- [验收标准](./docs/product/acceptance-criteria.md)
- [第二阶段验收](./docs/product/stage-2-acceptance.md)
- [第三阶段验收](./docs/product/stage-3-acceptance.md)
- [第四阶段首个增量](./docs/product/stage-4-agent-increment.md)
- [第四阶段验收](./docs/product/stage-4-acceptance.md)
- [第五阶段安全闭环验收](./docs/product/stage-5-acceptance.md)
- [第六阶段全栈体验验收](./docs/product/stage-6-acceptance.md)
- [第七阶段工程质量验收](./docs/product/stage-7-acceptance.md)
- [第八阶段交付验收](./docs/product/stage-8-acceptance.md)
- [确定性基线 ADR](./docs/adr/0001-deterministic-modular-monolith.md)
- [混合 RAG ADR](./docs/adr/0002-pgvector-hybrid-retrieval-and-local-bge.md)
- [受控 Agent ADR](./docs/adr/0003-provider-neutral-langgraph-agent.md)
- [LLM Provider 选型决策](./docs/adr/0004-primary-llm-provider.md)
- [可恢复会话与工单幂等 ADR](./docs/adr/0005-recoverable-conversation-and-ticket-confirmation.md)
- [本地 JWT 与人工工单闭环 ADR](./docs/adr/0006-local-jwt-and-human-ticket-workflow.md)
- [SSE、OTLP 与容器交付 ADR](./docs/adr/0007-sse-console-otel-and-container-delivery.md)

以下阶段学习说明保留对应阶段完成时的讲解与当时边界；当前验证口径以[最终证据快照](./docs/evaluation/final-evidence.md)为准。

- [第二阶段学习说明](./docs/learning/stage-2-deterministic-baseline.md)
- [第三阶段学习说明](./docs/learning/stage-3-hybrid-rag.md)
- [第四阶段学习说明](./docs/learning/stage-4-agent-increment.md)
- [第五阶段学习说明](./docs/learning/stage-5-security-loop.md)
- [第六阶段学习说明](./docs/learning/stage-6-fullstack-console.md)
- [第七阶段学习说明](./docs/learning/stage-7-engineering-quality.md)
- [第三阶段离线评测](./docs/evaluation/stage-3-rag-evaluation.md)
- [第四阶段 Qwen 冒烟评测](./docs/evaluation/stage-4-qwen-smoke-evaluation.md)
- [第四阶段 Agent 80 场景评测](./docs/evaluation/stage-4-agent-evaluation.md)
- [最终证据快照](./docs/evaluation/final-evidence.md)
- [系统架构](./docs/architecture/system-overview.md)
- [项目复盘](./docs/retrospectives/project-retrospective.md)
- [指标口径与证据索引](./docs/evaluation/metrics-and-claims.md)
- [技术讲解与设计问答](./docs/architecture/technical-guide.md)
- [第九阶段验收](./docs/product/stage-9-acceptance.md)
- [claim 级引用与忠实度 ADR](./docs/adr/0008-claim-level-citations-and-faithfulness-verification.md)
- [第九阶段忠实度评测](./docs/evaluation/stage-9-faithfulness-evaluation.md)
- [第九阶段学习说明](./docs/learning/stage-9-evidence-faithfulness.md)
- [第十阶段 Agent 中止与重试验收](./docs/product/stage-10-acceptance.md)
- [Agent SSE 中止与幂等重试 ADR](./docs/adr/0009-agent-sse-abort-and-idempotent-retry.md)
- [第十阶段学习说明](./docs/learning/stage-10-agent-abort-recovery.md)
- [第十一阶段工单队列验收](./docs/product/stage-11-acceptance.md)
- [工单队列游标分页 ADR](./docs/adr/0010-ticket-queue-cursor-pagination.md)
- [第十一阶段学习说明](./docs/learning/stage-11-ticket-queue-pagination.md)
- [第十二阶段 Agent Checkpoint 验收](./docs/product/stage-12-acceptance.md)
- [Agent 运行级 Checkpoint ADR](./docs/adr/0011-agent-run-checkpoints-and-resume.md)
- [第十二阶段 Checkpoint 评测](./docs/evaluation/stage-12-agent-checkpoint-evaluation.md)
- [第十二阶段学习说明](./docs/learning/stage-12-agent-run-checkpoints.md)
- [第十三阶段 SSE 回放验收](./docs/product/stage-13-acceptance.md)
- [SSE 事件持久化与回放 ADR](./docs/adr/0012-persisted-sse-events-and-replay.md)
- [第十三阶段 SSE 回放评测](./docs/evaluation/stage-13-sse-event-replay-evaluation.md)
- [第十三阶段学习说明](./docs/learning/stage-13-sse-event-replay.md)
- [第十四阶段前端断线恢复验收](./docs/product/stage-14-acceptance.md)
- [前端 SSE 断线恢复 ADR](./docs/adr/0013-frontend-stream-recovery.md)
- [第十四阶段恢复评测](./docs/evaluation/stage-14-frontend-stream-recovery-evaluation.md)
- [第十四阶段学习说明](./docs/learning/stage-14-frontend-stream-recovery.md)
- [第十五阶段保留与恢复锁验收](./docs/product/stage-15-acceptance.md)
- [历史保留与恢复锁 ADR](./docs/adr/0014-agent-history-retention-and-resume-guard.md)
- [第十五阶段清理评测](./docs/evaluation/stage-15-retention-and-resume-guard-evaluation.md)
- [第十五阶段学习说明](./docs/learning/stage-15-retention-and-resume-guard.md)
- [第十六阶段可观测性与维护验收](./docs/product/stage-16-acceptance.md)
- [OTLP 指标与定时维护 ADR](./docs/adr/0015-otel-metrics-and-scheduled-maintenance.md)
- [第十六阶段可观测性评测](./docs/evaluation/stage-16-observability-evaluation.md)
- [第十六阶段学习说明](./docs/learning/stage-16-observability-and-maintenance.md)
- [运维手册](./docs/operations/runbook.md)
- [第十七阶段 Cookie 会话验收](./docs/product/stage-17-acceptance.md)
- [Cookie 会话与 CSRF ADR](./docs/adr/0016-cookie-sessions-and-csrf.md)
- [第十七阶段会话评测](./docs/evaluation/stage-17-cookie-session-evaluation.md)
- [第十七阶段学习说明](./docs/learning/stage-17-cookie-sessions-and-csrf.md)
- [第十八阶段会话生命周期验收](./docs/product/stage-18-acceptance.md)
- [会话生命周期与清理 ADR](./docs/adr/0017-browser-session-lifecycle-and-pruning.md)
- [第十八阶段会话清理评测](./docs/evaluation/stage-18-session-lifecycle-evaluation.md)
- [第十八阶段学习说明](./docs/learning/stage-18-session-lifecycle.md)
