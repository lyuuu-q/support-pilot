# 第十三阶段评测：SSE 事件持久化与回放

- 运行时间：2026-10-12（Asia/Shanghai）
- Provider：deterministic / keyword-router-v1
- 数据性质：集成测试与合成数据，不是生产数据

## 验证结果

| 检查 | 结果 |
|---|---|
| SSE event id 格式 | `{run_id}:{sequence}` |
| progress 事件数量 | 4 |
| result 事件数量 | 1 |
| 完整回放 | sequence 1..5 连续 |
| after=2 | 只返回 sequence 3..5 |
| 非所有者 | 404 |
| 恢复运行追加事件 | 通过 |
| 后端完整测试 | 118 passed |
| Agent API 集成测试 | 20 passed |
| Alembic upgrade/check | 通过 |

## 机器验证

- `tests/integration/test_agent_api.py`
  - `test_agent_stream_assigns_monotonic_event_ids`
  - `test_agent_run_events_replay_after_sequence`

## 边界

- 回放接口返回 JSON，不是直接续传 SSE；
- 前端尚未自动调用回放；
- 事件清理和保留期限未实现；
- 事件数量、延迟和存储量随运行节点数增长。
