# Agent 运行级 Checkpoint 执行计划

**目标：** 使用 Alembic 管理的 PostgresSaver 表，为 `AgentRun` 保存节点级 checkpoint，并提供恢复 API。
**ADR：** `docs/adr/0011-agent-run-checkpoints-and-resume.md`

## 步骤

- [x] 增加 langgraph-checkpoint-postgres 依赖并保持官方锁源；
- [x] 迁移 0008 创建 checkpoint 表；
- [x] Alembic include_object 忽略第三方 checkpoint 表；
- [x] 迁移 0009 允许 interrupted 状态；
- [x] 使用 AgentRun.id 作为 thread_id；
- [x] 节点完成后持久化 trace；
- [x] 新增恢复 API；
- [x] 覆盖 checkpoint 存在、恢复、重复恢复、非所有者、无 checkpoint；
- [x] 更新 ADR、学习文档和验收；
- [x] 运行完整后端、Agent 评测和 E2E 回归。

## 完成定义

- [x] checkpoint 表由 Alembic 创建且 check 无漂移；
- [x] 运行结束后可以从最后节点恢复；
- [x] 重复恢复和越权有明确错误；
- [x] AgentConversation 仍是业务真相源；
- [x] 80 场景和 E2E 不回归。
