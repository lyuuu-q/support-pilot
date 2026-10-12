# 第十三阶段：SSE 事件持久化与回放验收

状态：已实现事件表、SSE event id 和所有者回放 API
验证日期：2026-10-12

## 1. 交付范围

- [x] 迁移 0010 创建 agent_run_events；
- [x] AgentStreamEvent 携带 event_id 和 sequence；
- [x] 正常和恢复运行持久化 progress/result；
- [x] event id 使用 run_id:sequence；
- [x] GET /agent/runs/{run_id}/events；
- [x] after 过滤和 limit；
- [x] 所有者校验；
- [x] 完整回放、越权和迁移测试。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S13-AC-01 | SSE id 单调且与 run id 一致 | `test_agent_stream_assigns_monotonic_event_ids` |
| S13-AC-02 | 事件可完整回放 | `test_agent_run_events_replay_after_sequence` |
| S13-AC-03 | after 只返回后续事件 | 同上 |
| S13-AC-04 | 非所有者读取 404 | 同上 |
| S13-AC-05 | 恢复运行追加新事件 | checkpoint 恢复测试 |
| S13-AC-06 | 迁移 check 无漂移 | `uv run alembic check` |

## 3. 结果

- 后端完整测试：118 passed；
- Agent API 集成测试：20 passed；
- 事件序列连续，回放与流一致；
- Alembic upgrade/check 通过。

## 4. 边界

- 当前是回放 API，不是自动续传 SSE；
- 前端尚未消费回放接口；
- 没有事件清理、压缩和保留期限；
- 未验证大事件量下的存储和分页。
