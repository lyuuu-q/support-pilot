# 第十八阶段评测：会话生命周期与清理

- 运行时间：2026-10-14（Asia/Shanghai）
- 数据库：PostgreSQL 16 + pgvector（localhost:54329 / 54330）
- 数据性质：合成用户与合成会话，不是生产流量
- 浏览器：Playwright 自带 Chromium v1243（与 CI 一致）

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 59 个源码文件无问题 |
| 后端完整测试 | 136 passed（新增 9） |
| 前端单测 | 14 passed（新增 1） |
| 前端 lint / 生产构建 | 通过（JS gzip 65.9 kB） |
| 浏览器端到端 | 1 passed（5.3s） |
| `alembic check` | 无漂移（本阶段无新迁移） |

## 会话管理行为

| 场景 | 结果 |
|---|---|
| `GET /auth/sessions` | 返回 2 条活跃会话，其中恰好 1 条标记为当前 |
| 撤销非当前会话 | 204；当前会话 `/auth/me` 仍 200，被撤销会话的旧 Cookie 变 401 |
| 撤销他人会话 | 404 |
| 撤销请求缺少 CSRF 头 | 403 `csrf_token_invalid` |
| `POST /auth/logout-all` | 204；所有会话行 `status=revoked`；旧访问 Cookie 401；写入 `auth.session.revoke_all` 审计 |

## 清理行为

| 场景 | 结果 |
|---|---|
| dry-run（含 1 条 90 天前过期、1 条活跃） | `deleted_sessions=1`、`active_sessions=1`，行数不变 |
| 真实清理（120 天前过期、45 天前过期且 revoked、活跃） | `deleted_sessions=2`，活跃会话保留，`active_sessions=1` |
| 批量上限 2、3 条候选 | `deleted_sessions=2`，剩余 1 条 |

`scripts/run_maintenance.ps1` 默认 dry-run 实跑输出：

- Agent 段：`deleted_events=0`、`deleted_runs=0`、`deleted_threads=0`、`dry_run=true`
- 会话段：`deleted_sessions=0`、`active_sessions=0`、`dry_run=true`
- 日志写入 `logs/maintenance-<时间戳>.log`（被 Git 忽略）

## 指标

- `support_pilot.auth.sessions_started`
- `support_pilot.auth.sessions_revoked`（`reason` 标签：logout / owner / logout_all）
- `support_pilot.auth.sessions_pruned`（`dry_run` 标签）
- Span：`auth.sessions.prune`

## 边界

- 合成数据、本机单实例，不代表生产会话规模；
- 未验证多标签页同时登出、长时间挂机后 refresh 竞争等浏览器边界；
- 清理脚本仍需外部计划任务；本阶段没有自动调度；
- 会话展示不含 IP 与设备指纹。
