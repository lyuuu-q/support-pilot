# 可观测性与定时维护执行计划

**目标：** 让 Agent、RAG 和清理任务产生指标信号，并提供可重复执行的维护脚本。
**ADR：** `docs/adr/0015-otel-metrics-and-scheduled-maintenance.md`

## 步骤

- [x] 增加 OTLP Metrics 装配与 metrics endpoint 配置；
- [x] `agent.run`、`agent.resume` Span 与 Agent 指标；
- [x] `rag.retrieval` Span 与 RAG 指标；
- [x] `agent.retention.prune` Span 与清理指标；
- [x] 增加 OTel Collector 配置与 Compose observability profile；
- [x] 增加维护脚本（默认 dry-run，日志入 logs/）；
- [x] 编写运维 Runbook；
- [x] 更新 ADR、评测、验收和学习文档；
- [x] 运行完整回归。

## 完成定义

- [x] OTel 启用时同时导出 Trace 与 Metrics；
- [x] OTel 关闭时埋点为 no-op，不产生网络请求；
- [x] 指标标签有界；
- [x] Collector 可启动并收到真实请求的 Trace 与 Metric；
- [x] 维护脚本默认 dry-run，显式 `-Execute` 才删除；
- [x] 文档记录 debug exporter 与定时任务边界。
