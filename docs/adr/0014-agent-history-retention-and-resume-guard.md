# ADR 0014：Agent 历史保留策略与并发恢复保护

- 状态：Accepted
- 日期：2026-10-12

## 背景

Checkpoint 和 SSE 事件表会随运行数量持续增长。与此同时，`resume` 只检查状态，两个并发请求可能同时开始恢复同一运行。

## 决策

1. 恢复时使用 `SELECT ... FOR UPDATE` 锁定 `AgentRun` 行。
2. 锁内把状态改为 `resuming` 后提交；第二个请求看到 `resuming` 会返回 400。
3. 如果进程在 `resuming` 状态崩溃，超过 `agent_resume_stale_seconds` 后允许再次恢复。
4. 增加运行和事件保留配置：
   - `agent_run_retention_days` 默认 30 天；
   - `agent_run_event_retention_days` 默认 7 天；
   - `agent_run_prune_batch_size` 默认 500。
5. 清理只删除处于终态的旧运行；`running/resuming/interrupted` 永不自动删除。
6. 事件清理排除活跃运行的事件，避免破坏断线回放。
7. 删除运行前先删除对应 PostgresSaver thread；检查点被放弃时记录为未删除。
8. 提供 `scripts/prune_agent_history.py`，默认 dry-run 支持显式安全检查。

## 代价与限制

- 清理是批处理脚本，不是自动定时任务；
- 删除历史会丢失旧运行的事件回放能力；
- 当前没有软删除和导出归档；
- 并发锁依赖 PostgreSQL 行锁，不适用于未来多数据库切换；
- stale 恢复窗口需要结合部署故障时间调优。

## 验证方式

- 两个并发恢复请求只允许一个成功；
- 过期 `resuming` 运行可以恢复；
- dry-run 不修改数据；
- 旧终态运行和事件被删除；
- running/interrupted 运行及其事件保留；
- 迁移、121 项后端测试和 E2E 通过。
