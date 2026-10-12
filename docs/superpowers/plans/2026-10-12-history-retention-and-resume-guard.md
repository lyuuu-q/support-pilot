# Agent 历史保留与恢复锁执行计划

**目标：** 防止 checkpoint/事件无限增长，并保证同一运行不会被并发恢复。
**ADR：** `docs/adr/0014-agent-history-retention-and-resume-guard.md`

## 步骤

- [x] 扩展 AgentRun 状态允许 resuming；
- [x] 恢复时行锁并设置 resuming；
- [x] stale resuming 运行可重新恢复；
- [x] 增加运行/事件保留配置；
- [x] 实现 prune_agent_history；
- [x] dry-run 和真实删除测试；
- [x] 增加运维脚本；
- [x] 更新 ADR、评测、验收和学习文档；
- [x] 运行完整回归。

## 完成定义

- [x] 并发恢复只有一个成功；
- [x] stale 恢复可用；
- [x] 活跃运行和事件不被清理；
- [x] 终态旧运行、事件和 checkpoint thread 被清理；
- [x] dry-run 可预检查。
