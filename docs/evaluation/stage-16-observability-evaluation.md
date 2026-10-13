# 第十六阶段评测：可观测性与定时维护

- 运行时间：2026-10-13（Asia/Shanghai）
- 数据库：PostgreSQL 16 + pgvector（localhost:54329 / 54330）
- Collector：otel/opentelemetry-collector:0.121.0（Compose observability profile）
- 数据性质：本机合成请求，不是生产流量

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 57 个源码文件无问题 |
| 后端完整测试 | 122 passed |
| 观测与清理聚焦测试 | 4 passed |
| `docker compose config` | 通过 |
| Collector 启动 | debug exporter 正常输出 |
| 真实 Agent 请求 Span | Collector 收到 40 spans |
| 真实 Agent 请求 Metric | Collector 收到 10 metrics / 14 data points |
| 集成测试 Span | `agent.run`、`rag.retrieval` 均出现 |
| 集成测试指标 | `support_pilot.agent.runs`、`agent.duration_ms`、`rag.searches` 均出现 |

## 观测信号

Span：

- `agent.run`：provider、model、outcome、intent、risk_level；
- `agent.resume`：run id、outcome；
- `rag.retrieval`：answerable、reason、hit_count；
- `agent.retention.prune`：dry_run。

指标：`support_pilot.agent.runs`、`agent.duration_ms`、`agent.resumes`、`agent.resume_duration_ms`、`rag.searches`、`rag.search_duration_ms`、`rag.hit_count`、`retention.deleted_events`、`retention.deleted_runs`、`retention.deleted_threads`。

## 边界

- Collector 只有 debug exporter，未接 Jaeger/Prometheus 等持久化后端；
- 样本是本机小流量，Span/Metric 计数只证明链路可用，不代表生产吞吐或 SLO；
- 未配置采样、导出周期调优与告警规则；
- 定时维护依赖部署方创建 Task Scheduler 任务，脚本默认 dry-run。
