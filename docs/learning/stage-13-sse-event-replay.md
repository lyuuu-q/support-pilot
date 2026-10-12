# 第十三阶段学习说明：SSE 事件持久化与回放

## 为什么 checkpoint 还不够

checkpoint 保存的是图执行状态，不是“用户已经看到哪些事件”。断线后即使用户继续恢复运行，也无法重建之前的节点 Trace。事件表把展示事实和恢复事实分开保存。

## 事件 identity 为什么用 run_id:sequence

- run_id 保证不同 API 运行不会冲突；
- sequence 在单个 run 内单调递增；
- SSE id 与数据库回放 id 完全一致，后续可以支持 Last-Event-ID。

## 为什么回放必须做权限校验

Agent 事件包含回答、引用、工具结果和 Trace。回放接口按 run 所有者校验，非所有者直接返回 404，避免通过 run id 猜测读取他人对话。

## 恢复和回放的关系

- 回放：读取已经发生的 progress/result；
- 恢复：从 checkpoint 继续尚未完成的图；
- 二者结合才能实现真正的断线续传。

## 当前状态

服务端事件持久化和回放 API 已完成，前端自动调用回放/续传仍是下一增量。

## 验收结果

- 后端完整测试：118 passed；
- Agent API 集成测试：20 passed；
- SSE id 单调且与 run id 一致；
- after 过滤和非所有者拒绝通过；
- Alembic upgrade/check 通过。
