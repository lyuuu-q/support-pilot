# 第十六阶段：可观测性与定时维护验收

状态：已实现 OTLP 指标埋点、Collector 与维护脚本
验证日期：2026-10-13

## 1. 交付范围

- [x] OTLP Metrics 装配（MeterProvider + PeriodicExportingMetricReader）；
- [x] metrics endpoint 配置；
- [x] `agent.run`、`agent.resume` Span 与 Agent 指标；
- [x] `rag.retrieval` Span 与 RAG 指标；
- [x] `agent.retention.prune` Span 与清理指标；
- [x] OTel Collector 配置与 Compose observability profile；
- [x] 维护脚本（默认 dry-run，日志入 logs/）；
- [x] 运维 Runbook；
- [x] 单元与集成测试；
- [x] ADR、评测、学习文档。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S16-AC-01 | 启用时装配 Trace 与 Metrics Exporter | `tests/unit/test_telemetry.py` |
| S16-AC-02 | 关闭时不装配，埋点为 no-op | 同上（默认分支） |
| S16-AC-03 | Agent 请求产生 `agent.run` Span | `tests/integration/test_observability.py` |
| S16-AC-04 | 检索产生 `rag.retrieval` Span | 同上 |
| S16-AC-05 | Agent/RAG 指标出现 | 同上（InMemoryMetricReader） |
| S16-AC-06 | Collector 收到真实 Trace/Metric | 40 spans、10 metrics / 14 points |
| S16-AC-07 | 维护脚本默认 dry-run | 第十五阶段清理测试 + Runbook |
| S16-AC-08 | Compose 配置合法 | `docker compose config --quiet` |

## 3. 结果

- 后端完整测试：122 passed；
- Ruff、Mypy（57 文件）通过；
- Compose config 通过，Collector 容器可启动；
- 真实 Agent 请求触发 40 spans 与 10 metrics / 14 data points。

## 4. 边界

- Collector 仅 debug exporter，无持久化或查询后端；
- 未配置告警、采样与导出周期调优；
- 计数来自本机合成流量，不代表生产 SLO；
- 定时任务需要部署方通过 Task Scheduler 自行创建；
- 清理默认 dry-run，活跃运行及其事件不清理。
