# ADR 0012：SSE 事件持久化与回放

- 状态：Accepted
- 日期：2026-10-12

## 背景

SSE 进度和结果原来只在响应流中存在；连接中断后，客户端只能重新发起整轮请求。AgentRun 已有 checkpoint，但缺少“已经推送到哪个事件”的持久化事实。

## 决策

1. 新增 `agent_run_events` 表，按 `run_id + sequence` 唯一保存 progress/result 事件。
2. `AgentStreamEvent` 携带 `event_id`，格式固定为 `{run_id}:{sequence}`。
3. 正常运行和恢复运行都写入事件，保证回放序列连续。
4. 新增 `GET /agent/runs/{run_id}/events?after=&limit=`，只允许运行所有者读取。
5. 事件 payload 存储结构化 JSON；结果事件保存完整 AgentResponse。
6. SSE `id:` 使用与数据库相同的 event id，为 Last-Event-ID 续传保留一致标识。
7. 当前提供事件回放 API；前端自动重连和 Last-Event-ID 续传留到下一增量。

## 备选方案

- 只依赖 checkpoint：只能恢复图状态，不能重放已经展示过的节点 Trace；
- 内存队列：实现简单，但进程重启后丢失；
- 把每个事件写 JSON 文件：不利查询、权限和清理。

## 代价与限制

- 每个节点事件增加一次数据库写入；
- 尚无事件清理和保留期限；
- 回放接口是 JSON，不直接恢复 SSE 长连接；
- 前端尚未自动使用回放结果，当前只完成服务端契约和验证。

## 验证方式

- SSE event id 使用 run id 前缀并单调递增；
- 流结束后事件可按 sequence 完整回放；
- `after=2` 只返回后续事件；
- 非所有者返回 404；
- 恢复运行会追加新事件；
- Alembic check 与完整回归通过。
