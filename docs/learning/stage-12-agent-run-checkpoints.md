# 第十二阶段学习说明：Agent 运行级 Checkpoint

## 为什么需要 checkpoint

跨轮会话状态回答的是“下一轮该做什么”，不是“这次运行执行到了哪个节点”。如果一次运行在第 3 个节点失败，只有 checkpoint 才能让第 4 个节点继续，而不是从头重跑。

## 两个状态源如何分工

- `AgentConversation`：业务事实，回答缺参、确认、工单和 Key 哈希；
- PostgresSaver checkpoint：LangGraph 执行事实，回答 thread、checkpoint、next node。

把它们混在一起会让 API、审计和迁移都失去边界。

## thread_id 为什么用 AgentRun.id

一个 session 有多轮运行。共享 thread_id 会让第二轮继承第一轮的图状态，造成历史污染。使用 run id 后，每次 API 运行独立，恢复时用同一个 run id 找回原线程。

## checkpoint 表为什么由迁移创建

官方 `PostgresSaver.setup()` 适合脚本式初始化，但项目要求数据库结构可追踪。迁移 0008 执行官方 `MIGRATIONS`，迁移 0009 扩展 run 状态；Alembic `include_object` 忽略这些第三方表，避免 check 把它们识别成删除。

## 恢复语义

恢复只允许：

- 原运行所有者；
- `running` 或 `interrupted` 状态；
- 存在 checkpoint。

恢复使用 `graph.stream(None, config)`，从 `snapshot.next` 继续。已完成运行再次恢复返回 400，避免把恢复当作任意结果读取接口。

## 代价

节点完成后提交 trace 和 checkpoint，会显著增加延迟：deterministic 80 场景 p50 从约 46ms 提升到约 700ms。这是用延迟换可恢复性。并发恢复锁、checkpoint 清理和保留策略仍是后续工作。

## 验收结果

- 后端完整测试：117 passed；
- checkpoint 存在、恢复、重复恢复、非所有者、无 checkpoint：通过；
- 80 场景：80/80，重复副作用和高风险误执行均为 0；
- Chromium E2E：1 passed；
- Alembic upgrade/check：通过。
