# ADR 0011：Agent 运行级 checkpoint 与恢复

- 状态：Accepted
- 日期：2026-10-12

## 背景

`AgentConversation` 能恢复跨轮业务事实，但一次 LangGraph 运行如果在中间失败，只能整轮重跑。前一轮评估发现官方 `langgraph-checkpoint-postgres` 可用，但需要解决依赖锁源和 checkpoint 表不由 Alembic 管理的问题。

## 决策

1. 使用官方 `PostgresSaver`，thread_id 固定为 `AgentRun.id`，每次 API 运行独立。
2. 保留 `AgentConversation` 为业务状态唯一真相源；checkpoint 只保存 LangGraph 节点状态。
3. 迁移 `0008` 执行 `PostgresSaver.MIGRATIONS` 创建 checkpoint 表；`CONCURRENTLY` 语句使用 Alembic autocommit block。
4. Alembic `include_object` 忽略 checkpoint 表，避免 autogenerate 将它们识别为删除。
5. 迁移 `0009` 扩展 `agent_runs.status`，允许 `interrupted`。
6. 运行开始时提交 run 行；每个节点完成后更新 trace/state。
7. 异常时标记 `interrupted`，保留 checkpoint；恢复 API 只允许运行所有者继续。
8. 恢复使用 `graph.stream(None, config)` 从最后完成节点继续。

## 代价与限制

- 节点完成后提交 trace，增加数据库写入和延迟；80 场景 p50 从约 46ms 提升到约 700ms；
- 只能从最后完成节点恢复，不能恢复执行到一半的节点；
- 只能保证 at-least-once，副作用仍依赖幂等键；
- checkpoint 清理、保留期限和并发恢复锁仍需后续补强；
- 当前恢复 API 返回 JSON，不做 SSE 重放。

## 验证方式

- 正常 Agent 运行写入 checkpoint 行；
- 标记 interrupted 后可以从 checkpoint 返回结果；
- 完成运行再次恢复返回 400；
- 非所有者和无 checkpoint 被拒绝；
- 80 场景评测仍为 80/80，重复副作用与高风险误执行均为 0；
- `alembic upgrade/check`、117 项后端测试和 E2E 通过。
