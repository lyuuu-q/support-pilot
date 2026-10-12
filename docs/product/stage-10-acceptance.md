# 第十阶段：Agent SSE 中止与幂等重试验收

状态：已实现浏览器中止、停止提示、安全重试和 SSE 事件 id
验证日期：2026-10-12

## 1. 交付范围

- [x] SSE 进度和结果增加 `id: {session_id}:{sequence}`；
- [x] `streamAgent` 接受 `AbortSignal`；
- [x] React 控制台提供“停止等待”和“重试上一步”；
- [x] 用户停止后明确提示服务器可能已完成；
- [x] 确认工单 Key 在停止重试期间保持不变；
- [x] 新问题或取消操作清除确认 Key；
- [x] 测试覆盖 signal 透传、停止重试和 SSE id。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S10-AC-01 | AbortSignal 传入 fetch | `frontend/src/api.test.ts` |
| S10-AC-02 | 停止等待后显示重试入口 | `frontend/src/App.test.tsx` |
| S10-AC-03 | SSE id 单调递增 | `tests/integration/test_agent_api.py` |
| S10-AC-04 | 相同确认 Key 返回同一工单 | `test_ticket_confirmation_is_idempotent_and_rejects_key_change` |
| S10-AC-05 | 不同确认 Key 返回 409 | 同上 |
| S10-AC-06 | 原业务闭环不回归 | Chromium E2E 1 passed |

## 3. 回归结果

- 后端：114 passed；
- 前端：6 项单元测试、lint、build 通过；
- Chromium E2E：1 passed；
- 未新增依赖，未改变业务 Alembic 模型。

## 4. 边界

- 浏览器中止不等于服务端取消；
- 当前不实现服务端事件回放；
- 节点级 checkpoint 和 PostgresSaver 尚未引入；
- 普通只读检索重试可能重复执行，写操作由幂等键保护。
