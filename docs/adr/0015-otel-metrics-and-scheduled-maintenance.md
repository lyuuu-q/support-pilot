# ADR 0015：OTLP 指标与定时维护

- 状态：Accepted
- 日期：2026-10-13

## 背景

第七阶段接入了 OTLP Trace，但只有 Span：能看到"一次请求经历了什么"，看不到"多久发生一次、耗时分布如何、失败率多高"。第十五阶段提供了 `scripts/prune_agent_history.py` 历史清理脚本，但仍需人工定时执行，且清理过程本身没有观测信号。

## 决策

1. 在 `configure_telemetry` 中同时装配 Trace 与 Metrics：
   - `TracerProvider` + `BatchSpanProcessor(OTLPSpanExporter)`；
   - `MeterProvider` + `PeriodicExportingMetricReader(OTLPMetricExporter)`；
   - 新增配置 `otel_exporter_otlp_metrics_endpoint`，默认 `http://localhost:4318/v1/metrics`。
2. 关键路径埋点四个 Span：
   - `agent.run`：provider、model、outcome、intent、risk_level；
   - `agent.resume`：run id、outcome；
   - `rag.retrieval`：answerable、reason、hit_count；
   - `agent.retention.prune`：dry_run。
3. 指标只使用有界标签（枚举或布尔），不把 run id、session id 等无界值写进标签，避免标签基数爆炸：
   - `support_pilot.agent.runs`（counter）、`support_pilot.agent.duration_ms`（histogram）；
   - `support_pilot.agent.resumes`、`support_pilot.agent.resume_duration_ms`；
   - `support_pilot.rag.searches`、`support_pilot.rag.search_duration_ms`、`support_pilot.rag.hit_count`；
   - `support_pilot.retention.deleted_events`、`deleted_runs`、`deleted_threads`。
4. OTel 未启用时不装配任何 Exporter；`get_tracer()/get_meter()` 返回 no-op，使埋点代码可以无条件调用而不产生副作用。
5. 提供 `ops/otel-collector.yaml`，在 Compose `observability` profile 下运行 `otel-collector`：OTLP HTTP receiver + batch processor + debug exporter。
6. 提供 `scripts/run_maintenance.ps1`：默认 dry-run，`-Execute` 才真正清理，日志写入被 Git 忽略的 `logs/`，保留期可参数覆盖。
7. 保留期默认值集中在配置：运行 30 天、事件 7 天、resume stale 300 秒。

## 代价与限制

- Collector 只有 debug exporter，Trace/Metric 只进日志，没有 Jaeger/Tempo/Prometheus 等持久化与查询后端；
- 指标属性与 Span 属性存在重叠，暂未做采样、导出周期调优和指标基数审查，也没有告警规则；
- 定时维护只是脚本加 Runbook，Windows Task Scheduler 任务需要部署方自行创建；
- 清理默认 dry-run，不自动执行，避免误删；
- 指标只在本机合成流量下验证，不能表述为生产 SLO 或容量结论。

## 验证方式

- 单元测试确认 Metrics Exporter/Provider 的装配；
- 集成测试确认 `agent.run`、`rag.retrieval` Span 与 Agent/RAG 指标；
- 真实 Collector 收到 40 spans、10 metrics / 14 data points；
- 维护脚本 dry-run 与真实清理行为由第十五阶段测试覆盖；
- Ruff、Mypy、122 项后端测试与 Compose config 通过。
