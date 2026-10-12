# 第十五阶段评测：历史保留与恢复锁

- 运行时间：2026-10-12（Asia/Shanghai）
- 数据库：PostgreSQL 16 + pgvector
- 数据性质：合成运行记录，不是生产数据

## 验证结果

| 检查 | 结果 |
|---|---|
| 并发恢复 | 1 个 200、1 个 400 |
| stale resuming 恢复 | 200 |
| dry-run 删除数 | 2 事件 / 1 运行，实际不删除 |
| 真实清理 | 1 事件 / 1 运行 / 1 checkpoint thread |
| 活跃运行保留 | 通过 |
| 活跃运行事件保留 | 通过 |
| 清理脚本 dry-run | 输出 JSON，删除数为 0 |
| Alembic upgrade/check | 通过 |
| 后端完整测试 | 121 passed |

## 脚本输出

`uv run python scripts/prune_agent_history.py --dry-run` 返回：

- `deleted_events: 0`
- `deleted_runs: 0`
- `deleted_threads: 0`
- `dry_run: true`

## 边界

- 清理未接入定时调度；
- 无归档导出；
- 删除历史后不能回放已清理运行；
- stale 恢复窗口未在生产故障数据上调优。
