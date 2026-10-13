# 指标后端与运维自动化执行计划

**目标：** 让指标离开 Collector 日志，成为可抓取、可告警、可留证的导出记录，并把维护流程自动化。
**ADR：** `docs/adr/0019-metrics-backend-and-ops-automation.md`

## 步骤

- [x] Collector 增加 Prometheus 导出端点（8889）；
- [x] Compose `observability` profile 增加 Prometheus 服务与抓取配置；
- [x] 告警规则 5 条（失败率、p95 延迟、不可回答比例、会话撤销、清理缺失）；
- [x] `scripts/metrics_snapshot.py` 指标快照脚本；
- [x] `scripts/register_maintenance_task.ps1` 计划任务注册脚本；
- [x] 配置一致性测试（含"告警指标必须在埋点中存在"）；
- [x] Ranbook 更新（端点、指标名对照表、快照、计划任务）；
- [x] 真实抓取并保存导出记录；
- [x] ADR、评测、验收、学习文档。

## 明确不做（记录取舍）

- **Firefox/WebKit 多浏览器 E2E**：原计划 P2 曾列为验收项。不做，理由：本机 CDN 按地区封锁无法获取这两个浏览器；Windows 上的 WebKit 并非 Safari，信号价值低；SSE/Cookie/OIDC 等关键路径已由 Chromium 真实浏览器用例 + 149 项后端测试覆盖。保留 Chromium 与系统浏览器通道。

## 完成定义

- [x] 指标可在 Collector 导出端点被抓取（真实数据，非空）；
- [x] 告警规则引用的指标全部真实存在（由测试保证）；
- [x] 不装 Prometheus 也有可提交的导出记录；
- [x] 维护流程有一条命令执行的计划任务注册脚本；
- [x] 全量测试与静态检查通过。
