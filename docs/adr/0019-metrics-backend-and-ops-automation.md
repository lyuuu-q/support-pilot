# ADR 0019：指标后端、告警规则与运维自动化

- 状态：Accepted
- 日期：2026-10-14

## 背景

第十六阶段接好了 OTLP Trace + Metrics，但 Collector 只有 debug exporter：指标只能"在日志里看见"，原计划 P3 验收里的"有可复现的指标看板或导出记录"并未满足；维护脚本也仍需要人工执行。本阶段补齐这两点。

## 决策

1. **Collector 暴露指标**：`ops/otel-collector.yaml` 增加 `prometheus` exporter（`0.0.0.0:8889`），指标管线输出 `[debug, prometheus]`；Trace 仍只走 debug（本地看日志）。
2. **可选 Prometheus**：Compose `observability` profile 增加 `prometheus` 服务（9090），挂载 `ops/prometheus.yml`（抓取 `otel-collector:8889`）与 `ops/alerting-rules.yml`。
3. **告警规则 5 条**：Agent 失败率 > 10%、Agent p95 延迟 > 5s、检索不可回答比例 > 50%、15 分钟内会话撤销 > 20、26 小时内没有清理执行。
4. **不装 Prometheus 也能留证**：`scripts/metrics_snapshot.py` 抓取导出端点并生成可提交的 JSON 快照（默认剔除 `instance`/`telemetry_sdk_*` 等噪声标签）。
5. **运维自动化**：`scripts/register_maintenance_task.ps1` 以管理员权限注册每日维护任务（`-At`、`-Remove`、`-WhatIf`）。
6. **防漂移测试**：`tests/unit/test_observability_config.py` 断言告警规则引用的每个 `support_pilot_*` 指标都能在 `telemetry.py` 的埋点里找到对应前缀。这条测试在本次实现中直接抓到了一个真实错误（见下）。

## 实测发现的坑（已修复并写进 Runbook）

Prometheus 导出会给 histogram 追加**单位后缀**：应用埋点 `support_pilot.agent.duration_ms`（单位 `ms`）实际导出为 `support_pilot_agent_duration_ms_milliseconds_bucket`，而 `support_pilot.rag.hit_count`（单位 `1`）保持 `support_pilot_rag_hit_count_bucket`。最初凭直觉写的 `..._duration_ms_bucket` 会永远匹配不到数据——这是"看板静默为空"的典型故障，现在由配置测试与 Runbook 名称对照表共同防住。

## 代价与限制

- 本机镜像加速源无法拉取 Prometheus 镜像，因此 **Prometheus 容器本身未在本机启动**；已验证的是 Collector 的导出端点、真实抓取到的序列、以及告警规则与埋点的一致性。具备镜像访问的环境可按 Runbook 直接启动；
- 只有 Prometheus 本地 TSDB，没有长期存储、Grafana 看板与 Alertmanager 通知；
- 告警阈值来自本机小流量经验值（如 p95 5 秒），未按生产流量校准；
- 快照是瞬时值，不含趋势与聚合区间；
- 计划任务脚本需要管理员权限，本机沙箱不能访问任务计划服务，未实际注册。

## 验证方式

- 真实抓取 `http://127.0.0.1:8889/metrics` 得到 114 条 `support_pilot_*` 序列、13 个指标族，并保存为 `docs/evaluation/results/metrics-snapshot-2026-10-14.json`；
- 造真实流量：Cookie 登录 → `/auth/me` → Agent 回答（1 条引用）→ 全部登出；
- 配置测试 5 项（Collector 端点、Compose 服务、Prometheus 抓取、告警指标一致性、Runbook 覆盖）；
- `docker compose config`、Ruff、Mypy、后端全量测试通过；维护脚本与注册脚本语法检查通过。
