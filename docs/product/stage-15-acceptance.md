# 第十五阶段：历史保留与恢复锁验收

状态：已实现保留清理脚本、dry-run 和并发恢复保护
验证日期：2026-10-12

## 1. 交付范围

- [x] resuming 状态与迁移 0011；
- [x] SELECT FOR UPDATE 行锁；
- [x] stale resuming 恢复；
- [x] 运行和事件保留配置；
- [x] prune_agent_history 服务；
- [x] checkpoint thread 删除；
- [x] 运维脚本 dry-run；
- [x] 并发和清理测试。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S15-AC-01 | 并发恢复只有一个成功 | `test_agent_resume_is_guarded_against_concurrent_calls` |
| S15-AC-02 | stale resuming 可恢复 | `test_stale_resuming_run_can_be_resumed` |
| S15-AC-03 | dry-run 不删除 | `test_prune_agent_history_dry_run_then_delete` |
| S15-AC-04 | 旧运行与事件清理 | 同上 |
| S15-AC-05 | 活跃运行与事件保留 | 同上 |
| S15-AC-06 | 迁移无漂移 | `uv run alembic check` |

## 3. 结果

- 后端完整测试：121 passed；
- 前端 10 项测试与 E2E 不回归；
- 清理脚本 dry-run 输出正常；
- 并发恢复安全边界通过。

## 4. 边界

- 未接定时任务；
- 未实现归档导出；
- 清理后历史不可回放；
- 仅验证 PostgreSQL 行锁方案。
