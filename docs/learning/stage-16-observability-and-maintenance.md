# 第十六阶段学习说明：可观测性与定时维护

## 为什么已经有 Trace 还要 Metrics

Trace（Span）回答"这一次请求发生了什么"，适合排查单次故障。它不适合回答"过去一小时多少次请求、多少失败、p95 多慢"——因为 Span 是离散事件，聚合成本高。Metrics 是聚合数值，天生用于趋势、告警和容量判断。两者互补：Trace 定位，Metrics 报警。

本阶段让 `configure_telemetry` 同时装配 TracerProvider 和 MeterProvider，用同一个 OTLP HTTP 端点族（`/v1/traces` 与 `/v1/metrics`）导出。

## 为什么要限制指标标签基数

指标标签的每个组合都会在 Collector 后端形成一条独立时间序列。如果把 `run_id`、`session_id` 写进标签，序列数会随请求量线性增长，内存和查询成本会失控。所以本阶段只使用有界标签：

- `outcome`、`intent`、`risk_level`、`result`、`reason` 都是固定枚举；
- `provider` 只有 deterministic / qwen 等少数取值；
- `answerable`、`dry_run` 是布尔。

需要用无界维度排查时，看对应 Span 的属性，而不是指标标签。

## 为什么关闭时也要能安全埋点

埋点代码分散在 Agent、RAG、清理三处。如果每处都写 `if settings.otel_enabled`，代码会充满分支且容易漏。OpenTelemetry 的 no-op provider 让 `get_tracer()/get_meter()` 在没有装配时返回空实现，`add/record` 调用被丢弃。因此埋点代码可以无条件执行，关闭 OTel 时既没有分支也没有网络请求。

## 指标清单

| 指标 | 类型 | 含义 |
|---|---|---|
| `support_pilot.agent.runs` | counter | Agent 运行次数（含 outcome/intent/risk_level） |
| `support_pilot.agent.duration_ms` | histogram | Agent 运行耗时 |
| `support_pilot.agent.resumes` | counter | 恢复次数（含 result） |
| `support_pilot.agent.resume_duration_ms` | histogram | 恢复耗时 |
| `support_pilot.rag.searches` | counter | 检索次数（含 answerable/reason） |
| `support_pilot.rag.search_duration_ms` | histogram | 检索耗时 |
| `support_pilot.rag.hit_count` | histogram | 命中数量分布 |
| `support_pilot.retention.deleted_events/runs/threads` | counter | 清理删除计数（含 dry_run） |

## 为什么 Collector 只用 debug exporter

引入 Jaeger/Prometheus 需要额外服务、存储和查询界面，属于交付目标之外。debug exporter 把接收到的 Trace/Metric 打到 Collector 日志，足以证明"埋点确实发出去了"，同时明确这是本地观测而非生产监控。要接真实后端时只需替换 exporter，不改应用代码。

## 为什么维护脚本默认 dry-run

删除历史不可逆。默认 dry-run 让操作者先看到删除量，再显式加 `-Execute` 才会写库。日志写入 `logs/`（已被 Git 忽略），便于留痕而不会污染仓库。

```powershell
.\scripts\run_maintenance.ps1                 # 只看删除量
.\scripts\run_maintenance.ps1 -Execute        # 真正清理
.\scripts\run_maintenance.ps1 -Execute -RunsOlderThanDays 60 -EventsOlderThanDays 14
```

Windows Task Scheduler 可按 Runbook 创建每日任务，但本阶段没有自动创建任务，也没有做失败告警。

## 验收结果

- 集成测试确认 `agent.run`、`rag.retrieval` Span 与 Agent/RAG 指标；
- 真实 Collector 收到 40 spans、10 metrics / 14 data points；
- Ruff、Mypy、122 项后端测试、Compose config 通过。
