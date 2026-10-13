# SupportPilot 运维手册

## 1. 启动 OTel Collector

Collector 使用 Compose `observability` profile：Trace 走 debug exporter（本地看日志），指标额外通过 Prometheus 导出端点暴露，供 Prometheus 抓取或脚本快照。

```powershell
docker compose --profile observability up -d otel-collector
```

同一个 profile 下还有 Prometheus（抓取 Collector 的指标并加载告警规则）：

```powershell
docker compose --profile observability up -d prometheus
# Prometheus UI: http://127.0.0.1:9090
```

不启动 Prometheus 也能取指标——Collector 已把指标以 Prometheus 文本格式暴露在 `http://127.0.0.1:8889/metrics`。

启用 API 埋点：

```powershell
$env:SUPPORT_PILOT_OTEL_ENABLED = 'true'
$env:SUPPORT_PILOT_OTEL_EXPORTER_OTLP_ENDPOINT = 'http://127.0.0.1:4318/v1/traces'
$env:SUPPORT_PILOT_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT = 'http://127.0.0.1:4318/v1/metrics'
uv run uvicorn support_pilot.main:app --reload
```

查看 Collector 输出：

```powershell
docker compose --profile observability logs -f otel-collector
```

容器内 API 连接宿主机 Collector 时使用：

```text
http://host.docker.internal:4318/v1/traces
http://host.docker.internal:4318/v1/metrics
```

## 2. Agent 关键 Span

- `agent.run`：一次 Agent 请求，包含 provider、model、outcome、intent、risk_level；
- `agent.resume`：一次恢复请求，包含 run id 和 outcome；
- `rag.retrieval`：一次混合检索，包含 answerable、reason、hit_count；
- `agent.retention.prune`：一次历史清理。

## 3. 关键指标

应用埋点使用点号命名；Prometheus 导出时点号转下划线，counter 追加 `_total`，histogram 追加单位与 `_bucket/_sum/_count`。例如：

| 应用埋点 | Prometheus 中的名字 |
|---|---|
| `support_pilot.agent.runs` | `support_pilot_agent_runs_total` |
| `support_pilot.agent.duration_ms` | `support_pilot_agent_duration_ms_milliseconds_bucket` |
| `support_pilot.rag.searches` | `support_pilot_rag_searches_total` |
| `support_pilot.auth.sessions_revoked` | `support_pilot_auth_sessions_revoked_total` |

生成一份可提交的指标快照（无需 Prometheus）：

```powershell
uv run python scripts/metrics_snapshot.py --output docs/evaluation/results/metrics-snapshot-<日期>.json
```

告警规则在 `ops/alerting-rules.yml`，覆盖 Agent 失败率、Agent p95 延迟、检索不可回答比例、会话撤销激增与"清理未执行"。

- `support_pilot.agent.runs`
- `support_pilot.agent.duration_ms`
- `support_pilot.agent.resumes`
- `support_pilot.agent.resume_duration_ms`
- `support_pilot.rag.searches`
- `support_pilot.rag.search_duration_ms`
- `support_pilot.rag.hit_count`
- `support_pilot.retention.deleted_events`
- `support_pilot.retention.deleted_runs`
- `support_pilot.retention.deleted_threads`

## 4. 定时维护

维护脚本一次执行两段清理：Agent 运行/事件/checkpoint，以及过期的浏览器会话。

每日 dry-run：

```powershell
.\scripts\run_maintenance.ps1
```

确认删除量后执行：

```powershell
.\scripts\run_maintenance.ps1 -Execute
```

自定义保留期：

```powershell
.\scripts\run_maintenance.ps1 -Execute -RunsOlderThanDays 60 -EventsOlderThanDays 14 -SessionsOlderThanDays 45
```

单独清理会话（默认 dry-run）：

```powershell
uv run python scripts/prune_auth_sessions.py --dry-run
uv run python scripts/prune_auth_sessions.py
```

会话保留期建议不小于 refresh 有效期（默认 30 天 vs 14 天）；清理只删除 `expires_at` 早于保留期的行，活跃会话不会被删除。

日志写入被 Git 忽略的 `logs/`。

Windows 计划任务可以用脚本注册（需要管理员权限的 PowerShell）：

```powershell
.\scripts\register_maintenance_task.ps1                 # 默认每日 03:30
.\scripts\register_maintenance_task.ps1 -At 04:15
.\scripts\register_maintenance_task.ps1 -Remove
```

等价的 Task Scheduler 操作是：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <repo>\scripts\run_maintenance.ps1 -Execute
```

## 5. 企业身份（OIDC）

启用条件（缺一不可）：`SUPPORT_PILOT_OIDC_ENABLED=true`、`SUPPORT_PILOT_OIDC_ISSUER`、`SUPPORT_PILOT_OIDC_CLIENT_ID`、`SUPPORT_PILOT_OIDC_REDIRECT_URI`。issuer 必须是 HTTPS，或回环地址上的 HTTP。

本地演示：

```powershell
uv run python scripts/dev_oidc_provider.py   # 开发用 IdP，127.0.0.1:18002
```

`scripts/dev_oidc_provider.py` 是内存态的**开发/测试**实现（启动时生成 RSA 密钥，校验 PKCE，只认三个合成账号），不能用于生产。

排障要点：

- `/auth/providers` 显示 `oidc.enabled=false`：检查启用开关与 issuer/client id 是否都配置（配置不全会直接拒绝启动）；
- 回调 400 `oidc_flow_failed`：多为 state 过期/重放、nonce 不符，或 redirect_uri 与 IdP 注册值不一致；
- 回调 403 `oidc_account_not_linked`：IdP 邮箱在本系统没有活跃账号，或该邮箱的 `email_verified` 为 false；
- 校验失败但 IdP 日志正常：确认 IdP 的签名算法是非对称（RS/ES），HS256 会被直接拒绝；
- 每次登录都会实时拉取 discovery 与 JWKS，IdP 不可达时登录会失败而不是降级。

## 6. 浏览器会话排障

- 登录后立刻 401：确认浏览器携带 `support_pilot_access`/`support_pilot_refresh` Cookie，且前后端同源（开发时走 Vite 代理）；
- 写操作 403 `csrf_token_invalid`：确认请求带 `X-CSRF-Token` 且等于 `support_pilot_csrf` Cookie 值；
- 用户被强制登出：refresh Cookie 只作用于 `/api/v1/auth`，检查反向代理是否改写路径前缀；
- 令牌被撤销后仍能访问：确认没有绕过 Cookie 路径使用 Bearer 令牌（Bearer 不校验会话状态，供脚本使用）；
- 生产 HTTPS 部署必须设置 `SUPPORT_PILOT_AUTH_COOKIE_SECURE=true`；
- 用户反映"被登出"：先查 `support_pilot.auth.sessions_revoked` 的 reason 标签，区分本人登出、单会话撤销与全部撤销；
- 会话数异常增长：检查客户端是否在循环中刷新（每次 refresh 都会新增一行）。

## 7. 故障排查

- Docker Engine 未启动：先启动 Docker Desktop，再执行 `docker compose ps`；
- Collector 无输出：确认 `SUPPORT_PILOT_OTEL_ENABLED=true` 且端点正确；
- 数据库连接失败：确认 `postgres`/`postgres-test` 容器 healthy；
- 清理脚本失败：先用默认 dry-run 检查，不要在保留期不确定时直接执行；
- 浏览器 E2E 无法启动：先用 `PLAYWRIGHT_BROWSERS_PATH` 指向已有缓存（本机为 `C:\Users\刘雨晴\Documents\github\.playwright-browsers`）；确实没有缓存且下载被阻断时，再设置 `E2E_BROWSER_CHANNEL=chrome`（或 `msedge`）使用系统浏览器，此时录屏会被关闭。
