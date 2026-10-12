# 第十二阶段评测：Agent 运行级 checkpoint

- 运行时间：2026-10-12（Asia/Shanghai）
- Provider：deterministic / keyword-router-v1
- 数据集：Agent 80 场景，91 个请求步骤
- 数据性质：人工标注合成场景，不是生产数据

## 指标

| 指标 | 结果 | 对比 |
|---|---:|---|
| 场景通过率 | 80/80 | 与 checkpoint 前一致 |
| Intent macro-F1 | 1.000 | 与 checkpoint 前一致 |
| 重复副作用 | 0 | 与 checkpoint 前一致 |
| 高风险误执行 | 0 | 与 checkpoint 前一致 |
| latency p50 | 698.45 ms | 接入前约 46 ms |
| latency p95 | 856.85 ms | 接入前约 58 ms |

延迟上升来自：

- 每个节点完成后提交 `AgentRun.trace_json/state_json`；
- PostgresSaver 每个节点写 checkpoint、blob 和 pending writes；
- 每个运行独立创建 saver 连接。

## 恢复验证

- 正常运行在 `checkpoints` 表写入对应 `thread_id`；
- 把完成运行标记为 `interrupted` 后，恢复接口返回原结果；
- 已完成运行再次恢复返回 400；
- 非所有者恢复返回 404；
- 无 checkpoint 的 interrupted 运行返回 400；
- Alembic upgrade/check 无漂移；
- 后端完整测试 117 passed；
- Chromium E2E 1 passed。

## 机器结果

`docs/evaluation/results/agent-scenarios-v1-checkpoint.json`

## 边界

- 只验证 deterministic Provider；
- 只保证从最后完成节点恢复，不能恢复执行到一半的节点；
- at-least-once 执行仍依赖工单和会话幂等；
- 尚未实现 checkpoint 清理、保留期限和并发恢复锁；
- 延迟数据来自本地单机 CPU/PostgreSQL，不代表生产容量。
