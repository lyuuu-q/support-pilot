# 第二十阶段学习说明：指标后端与运维自动化

## 从"日志里能看见"到"能被抓取"

上一阶段指标只在 Collector 日志里出现：人能看到，机器用不了。要做看板和告警，指标必须是**可抓取**的。这一阶段给 Collector 加了 Prometheus exporter：它把收到的 OTLP 指标改写成 Prometheus 文本格式，暴露在 `:8889/metrics`。Prometheus 抓它、脚本抓它、`curl` 也能抓它——这就是"导出记录"的最低成本形态。

两种形态的取舍很清楚：

| 方式 | 优点 | 代价 |
|---|---|---|
| push 到 Collector（现状） | 应用不用暴露端口、可批量、可加处理器 | 要有 Collector 才看得到 |
| 暴露成 Prometheus 端点 | 任何抓取器都能读，天然适合告警 | 多一个对外端口，需要访问控制 |

生产上通常两者结合：应用 push、Collector 暴露，抓取侧只暴露给监控网段。

## 一个真实的坑：单位后缀

应用埋点叫 `support_pilot.agent.duration_ms`，我第一版告警规则顺手写成 `support_pilot_agent_duration_ms_bucket`——结果永远查不到数据。实测抓取后发现导出名是：

```
support_pilot_agent_duration_ms_milliseconds_bucket
```

原因是 Prometheus 导出会给 histogram 加**单位的规范名**（`ms` → `milliseconds`），而单位是 `1` 的直方图（如 `rag.hit_count`）不加后缀。这类错误的危险之处在于：**规则语法合法、Prometheus 不报错、看板只是永远为空**，没人会发现。

防线是两层：Runbook 里放"应用埋点名 ↔ Prometheus 名"对照表；单元测试断言"告警规则里出现的每个指标前缀，都能在 `telemetry.py` 里找到对应埋点"。以后有人改埋点名或写错后缀，测试会直接失败。

## 告警怎么设计才不是噪音

本阶段五条规则都遵循同一套思路：

1. **用比率而不是绝对量**：失败数 5 次在小流量下毫无意义，失败率 > 10% 才有信息量；
2. **除以 `clamp_min(..., 0.0001)`**：流量为零时不产生 `0/0` 导致的假空值；
3. **给 `for`**：连续满足一段时间才触发，避免瞬时抖动；
4. **分级**：失败率/延迟是 warning，会话撤销激增与清理缺失是 info；
5. **在注解里写"下一步查什么"**：`description` 直接指向对应的 Span 或脚本，值班的人不用猜。

规则本身不发送通知（没有 Alertmanager），它只产生告警状态——这是本地演示的边界，不是设计目标。

## 为什么还要一个快照脚本

看板需要一套 Prometheus/Grafana 才有可能跑起来；而"我确实把指标接出来了"这个证据，用 30 行脚本就能留下：抓一次端点、剔掉 `instance`/`telemetry_sdk_*` 这类噪声标签、按指标族汇总成 JSON 提交进仓库。这样即使在没有 Prometheus 的机器上（比如这次的沙箱），也有可复核的导出记录，而不是一句"我看过日志"。

## 维护自动化

维护脚本此前只能人工执行。`register_maintenance_task.ps1` 用 `Register-ScheduledTask` 注册每日任务，支持 `-At` 调整时间、`-Remove` 反注册、`-WhatIf` 预演。注册需要管理员权限——本机沙箱无法访问任务计划服务，所以只做了语法校验，这一点已写进 ADR 边界。

## 验收结果

- 真实抓取：114 条 `support_pilot_*` 序列、13 个指标族；
- 造流量后读到的真实数值：Agent 运行 2 次（含 1 次带引用回答）、平均耗时 682ms、检索 2 次平均 45ms、命中 10 条、会话创建 1 次、全部撤销 1 次；
- 配置一致性测试 5 项通过；
- Ruff、Mypy、后端 154 项测试通过。

## 记录一个取舍：多浏览器不做

原计划 P2 写着"Playwright 覆盖 Chromium、Firefox、WebKit"。这次决定**不做并记录理由**：本机浏览器 CDN 按地区封锁、Windows 上的 WebKit 不是 Safari、关键路径已由 Chromium 真实用例覆盖。工程上"明确不做并说明原因"比"配置了但从未验证"更有价值——后者会让后来的人以为已经验证过。
