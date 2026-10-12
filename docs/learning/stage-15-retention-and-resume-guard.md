# 第十五阶段学习说明：历史保留与恢复锁

## 为什么 checkpoint 需要清理

checkpoint、blob 和事件表会随着每次运行持续增长。没有保留策略，数据库最终会被历史执行细节占满，业务查询和备份都会变慢。

## 为什么不能直接删除所有旧行

- `running/resuming/interrupted` 运行仍可能需要恢复；
- 活跃运行的旧事件仍可能用于断线回放；
- 删除 run 前必须处理对应的 checkpoint thread，否则会产生孤儿。

实现规则：

- 只删除终态且超过运行保留期的 run；
- 事件清理排除活跃 run；
- 删除 run 前调用 checkpointer `delete_thread`。

## 为什么恢复需要行锁

两个并发恢复请求如果都先读到 `interrupted`，就会同时开始执行图。行锁加状态迁移解决：

1. `SELECT ... FOR UPDATE` 锁定运行行；
2. 校验状态；
3. 改为 `resuming` 并提交；
4. 第二个请求看到 `resuming` 返回 400。

## stale 状态如何处理

如果进程在 `resuming` 时崩溃，状态会停在 `resuming`。超过 `agent_resume_stale_seconds` 后允许重新恢复，避免永久卡死；窗口需要按部署故障时间调整。

## 运维入口

```powershell
uv run python scripts/prune_agent_history.py --dry-run
uv run python scripts/prune_agent_history.py
```

## 验收结果

- 并发恢复：一个 200，一个 400；
- stale resuming：可恢复；
- dry-run：不修改数据；
- 旧终态运行、事件和 checkpoint thread：被清理；
- 活跃运行和事件：保留；
- 后端完整测试：121 passed。
