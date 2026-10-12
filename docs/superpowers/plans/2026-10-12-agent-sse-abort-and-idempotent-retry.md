# Agent SSE 中止与幂等重试执行计划

**目标：** 让用户能停止等待 Agent SSE，并在同一会话和同一确认 Key 下安全重试。
**ADR：** `docs/adr/0009-agent-sse-abort-and-idempotent-retry.md`

## 步骤

- [x] SSE 进度和结果增加 `id`，保持原 `event`/`data` 兼容；
- [x] `streamAgent` 支持 `AbortSignal`；
- [x] CustomerWorkspace 增加停止与重试状态；
- [x] 确认工单 Key 在停止重试期间保持不变；
- [x] 新意图清除旧确认 Key，避免串用；
- [x] 前端测试覆盖 signal、停止提示和重试；
- [x] 后端测试覆盖 SSE id 和同一 Key 幂等重放；
- [x] 更新学习文档、README 和验收标准；
- [x] 运行前端、后端和 E2E 回归。

## 完成定义

- [x] 用户可在浏览器中停止等待；
- [x] 停止后不会把部分结果显示为成功；
- [x] 确认重试不会产生第二张工单；
- [x] 不声称实现服务端 checkpoint 或事件回放；
- [x] 所有测试和静态检查通过。
