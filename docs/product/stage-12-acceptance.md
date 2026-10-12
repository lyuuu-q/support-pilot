# 第十二阶段：Agent 运行级 Checkpoint 验收

状态：已实现 PostgresSaver checkpoint、恢复 API 和 Alembic 迁移
验证日期：2026-10-12

## 1. 交付范围

- [x] 迁移 0008 创建官方 checkpoint 表；
- [x] 迁移 0009 允许 interrupted 状态；
- [x] AgentRun.id 作为 thread_id；
- [x] 运行开始持久化 AgentRun；
- [x] 节点完成后持久化 trace/state；
- [x] 恢复 API 和所有者校验；
- [x] 重复恢复、无 checkpoint、越权测试；
- [x] AgentConversation 与 checkpoint 职责分离。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S12-AC-01 | 正常运行写入 checkpoint | `test_agent_run_persists_checkpoint_and_can_be_resumed` |
| S12-AC-02 | interrupted 运行可恢复 | 同上 |
| S12-AC-03 | 完成运行重复恢复拒绝 | 同上 |
| S12-AC-04 | 非所有者恢复拒绝 | `test_agent_resume_rejects_non_owner_and_missing_checkpoint` |
| S12-AC-05 | 无 checkpoint 恢复拒绝 | 同上 |
| S12-AC-06 | migration check 无漂移 | `uv run alembic check` |
| S12-AC-07 | 80 场景和 E2E 不回归 | checkpoint 评测报告 |

## 3. 结果

- 后端完整测试：117 passed；
- Agent 80 场景：80/80；
- 重复副作用 0，高风险误执行 0；
- Chromium E2E：1 passed；
- p50/p95：约 698/857 ms，延迟上升已记录。

## 4. 边界

- 只支持从最后完成节点恢复；
- 不实现节点执行中的精确恢复；
- 当前恢复 API 不返回 SSE；
- checkpoint 清理、保留期限和并发恢复锁待后续实现。
