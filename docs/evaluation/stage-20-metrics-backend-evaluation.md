# 第二十阶段评测：指标后端与运维自动化

- 运行时间：2026-10-14（Asia/Shanghai）
- 环境：Windows 本机，PostgreSQL 16 + pgvector（localhost:54329），Collector 容器 `otel/opentelemetry-collector:0.121.0`
- 数据性质：合成流量（Cookie 登录 + 一次知识问答 + 全部登出），不是生产流量

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 60 个源码文件无问题 |
| 后端完整测试 | 154 passed（新增 5 项配置测试） |
| `docker compose --profile observability config --quiet` | 通过 |
| Collector 重启并加载新配置 | 成功 |
| `http://127.0.0.1:8889/metrics` | 114 条 `support_pilot_*` 序列、13 个指标族 |
| PowerShell 语法校验 | `run_maintenance.ps1`、`register_maintenance_task.ps1` 均 0 错误 |

## 造流量后读到的真实数值

| 指标 | 取值 |
|---|---|
| `support_pilot_agent_runs_total{outcome="answered",intent="knowledge",risk_level="R1"}` | 2 |
| `support_pilot_agent_duration_ms_milliseconds_count` / `_sum` | 2 / 1364.4 ms（平均约 682 ms） |
| `support_pilot_rag_searches_total{answerable="true",reason="sufficient_evidence"}` | 2 |
| `support_pilot_rag_search_duration_ms_milliseconds_sum` | 90.45 ms（平均约 45 ms） |
| `support_pilot_rag_hit_count_sum` | 10（每次约 5 条） |
| `support_pilot_auth_sessions_started_total` | 1 |
| `support_pilot_auth_sessions_revoked_total{reason="logout_all"}` | 1 |

（计数为 2 是因为本机同时有一个早先启动的 API 实例也在导出指标。）

导出记录：`docs/evaluation/results/metrics-snapshot-2026-10-14.json`。

## 实测发现的名称差异（已修正）

| 应用埋点 | 实际 Prometheus 名称 |
|---|---|
| `support_pilot.agent.duration_ms` | `support_pilot_agent_duration_ms_milliseconds_bucket` |
| `support_pilot.rag.hit_count` | `support_pilot_rag_hit_count_bucket`（单位 `1` 不加后缀） |

第一版告警规则写的是 `..._duration_ms_bucket`，永远不会命中——这类错误不会报错，只会让看板长期为空。现在由配置测试 + Runbook 对照表双重防护。

## 环境限制与处理

- 本机镜像加速源拉取 Prometheus 镜像长时间无进展（已终止），因此 **Prometheus 容器未启动**：`ops/prometheus.yml` 与 `ops/alerting-rules.yml` 只做到配置正确、并与真实埋点名称对齐，未做端到端抓取；
- 计划任务注册脚本需要管理员权限，本机沙箱无法访问任务计划服务，只做了语法校验；
- 应用指标导出周期为 60 秒（OTel SDK 默认），因此造流量后需要等待一个周期才能抓取到数据。

## 边界

- 合成流量、本机单实例，不代表生产规模与告警有效性；
- 无长期存储、看板与通知链路；
- 告警阈值未按真实流量校准，也未做"告警风暴"压测。
