# SupportPilot 运维手册

## 1. 启动 OTel Collector

Collector 使用 Compose `observability` profile，默认只导出到 debug exporter，适合本地查看 Trace/Metric。

```powershell
docker compose --profile observability up -d otel-collector
```

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
.\scripts\run_maintenance.ps1 -Execute -RunsOlderThanDays 60 -EventsOlderThanDays 14
```

日志写入被 Git 忽略的 `logs/`。

Windows Task Scheduler 可创建每日任务，操作使用：

```text
powershell.exe -NoProfile -ExecutionPolicy Bypass -File <repo>\scripts\run_maintenance.ps1 -Execute
```

## 5. 浏览器会话排障

- 登录后立刻 401：确认浏览器携带 `support_pilot_access`/`support_pilot_refresh` Cookie，且前后端同源（开发时走 Vite 代理）；
- 写操作 403 `csrf_token_invalid`：确认请求带 `X-CSRF-Token` 且等于 `support_pilot_csrf` Cookie 值；
- 用户被强制登出：refresh Cookie 只作用于 `/api/v1/auth`，检查反向代理是否改写路径前缀；
- 令牌被撤销后仍能访问：确认没有绕过 Cookie 路径使用 Bearer 令牌（Bearer 不校验会话状态，供脚本使用）；
- 生产 HTTPS 部署必须设置 `SUPPORT_PILOT_AUTH_COOKIE_SECURE=true`。

## 6. 故障排查

- Docker Engine 未启动：先启动 Docker Desktop，再执行 `docker compose ps`；
- Collector 无输出：确认 `SUPPORT_PILOT_OTEL_ENABLED=true` 且端点正确；
- 数据库连接失败：确认 `postgres`/`postgres-test` 容器 healthy；
- 清理脚本失败：先用默认 dry-run 检查，不要在保留期不确定时直接执行；
- 浏览器 E2E 无法启动：若 Playwright 自带 Chromium 下载失败，可设置 `E2E_BROWSER_CHANNEL=chrome`（或 `msedge`）使用系统浏览器，此时录屏会被关闭。
