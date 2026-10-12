# SSE 事件持久化与回放执行计划

**目标：** 持久化 Agent progress/result 事件，并提供所有者可读的事件回放 API。
**ADR：** `docs/adr/0012-persisted-sse-events-and-replay.md`

## 步骤

- [x] 新增 agent_run_events 迁移；
- [x] 引入 AgentStreamEvent 事件信封；
- [x] 正常和恢复运行持久化事件；
- [x] SSE id 改为 run_id:sequence；
- [x] 新增事件回放 API；
- [x] 覆盖完整回放、after 过滤和越权；
- [x] 更新学习文档和验收；
- [x] 运行完整后端和迁移回归。

## 完成定义

- [x] 事件序列在数据库中唯一且连续；
- [x] 回放与实际 SSE 事件一致；
- [x] 越权读取返回 404；
- [x] 恢复运行不产生重复 sequence；
- [x] 迁移 check 和全部测试通过。
