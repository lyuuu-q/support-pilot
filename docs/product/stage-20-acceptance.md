# 第二十阶段：指标后端与运维自动化验收

状态：已实现指标导出端点、Prometheus 抓取与告警配置、指标快照与计划任务脚本
验证日期：2026-10-14

## 1. 交付范围

- [x] Collector Prometheus 导出端点（`:8889/metrics`）；
- [x] Compose `observability` profile 下的 Prometheus 服务与抓取配置；
- [x] 5 条告警规则；
- [x] `scripts/metrics_snapshot.py` 指标快照；
- [x] `scripts/register_maintenance_task.ps1` 计划任务注册；
- [x] `tests/unit/test_observability_config.py` 配置一致性测试；
- [x] Runbook：端点、指标名对照表、快照命令、计划任务；
- [x] 导出记录 `docs/evaluation/results/metrics-snapshot-2026-10-14.json`。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S20-AC-01 | 指标可从导出端点真实抓取 | 114 条 `support_pilot_*` 序列 / 13 指标族 |
| S20-AC-02 | 造流量后指标出现对应取值 | Agent 2 次、平均 682ms、检索 2 次平均 45ms、会话创建/撤销各 1 |
| S20-AC-03 | 导出记录可提交、可复核 | `metrics-snapshot-2026-10-14.json` + `scripts/metrics_snapshot.py` |
| S20-AC-04 | 告警规则只引用真实埋点指标 | `test_alert_rules_only_reference_metrics_that_are_actually_emitted` |
| S20-AC-05 | Collector 配置暴露 prometheus exporter | `test_collector_exposes_prometheus_metrics_endpoint` |
| S20-AC-06 | Compose 定义 Prometheus 服务与挂载 | `test_compose_runs_prometheus_under_the_observability_profile` |
| S20-AC-07 | Prometheus 抓取 Collector 并加载规则 | `test_prometheus_scrapes_the_collector_and_loads_alert_rules` |
| S20-AC-08 | Runbook 覆盖端点、快照与计划任务 | `test_runbook_documents_the_metrics_endpoint_and_snapshot_script` |
| S20-AC-09 | Compose 配置合法 | `docker compose --profile observability config --quiet` |
| S20-AC-10 | 维护/注册脚本语法有效 | PowerShell Parser 校验 0 错误 |

## 3. 结果

- 后端完整测试：154 passed（新增 5 项配置测试）；
- Ruff、Mypy（60 文件）通过；
- Compose config 通过；Collector 用新配置重启并成功输出指标；
- 真实流量：Cookie 登录 → `/auth/me` → Agent 回答（1 条引用）→ 全部登出。

## 4. 边界

- **Prometheus 容器未在本机启动**：本机镜像加速源不可用，Prometheus 与告警规则只做到"配置正确 + 指标与规则一致"，未做端到端抓取验证；
- 无 Alertmanager，规则只产生告警状态；
- 无 Grafana 看板与长期存储；
- 告警阈值为本机小流量经验值，未按生产校准；
- 计划任务脚本未实际注册（需要管理员权限）；
- **多浏览器 E2E 决定不做**：原因见 `docs/superpowers/plans/2026-10-14-metrics-backend-and-ops-automation.md`。
