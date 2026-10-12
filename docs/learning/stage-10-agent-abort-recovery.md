# 第十阶段学习说明：Agent 中止与幂等重试

## 1. 为什么先做这个，而不是直接上 PostgresSaver

节点级 checkpoint 很有价值，但引入官方 PostgresSaver 会新增不由 Alembic 管理的表，并且当前 lock 更新会把全局依赖源改写成镜像。现有项目已经用显式会话状态解决缺参、确认和工单副作用，因此先补最直接的可用性缺口：用户无法停止等待，停止后又没有安全重试路径。

## 2. 为什么停止不等于取消

浏览器 `AbortSignal` 只停止当前 fetch。服务器可能已经完成某些节点，甚至已经创建工单。所以界面不能把停止显示成“什么都没发生”，而应提示“服务器可能已完成”，并让用户用同一 `session_id` 和确认 Key 重试。

## 3. 为什么确认 Key 必须稳定

确认工单如果每次重试都生成新 `Idempotency-Key`，服务器会把它当成新的写请求，可能创建第二张工单。实现方式：

- 第一次点击“确认创建工单”时生成随机 Key；
- 中止和重试期间保留同一个 Key；
- 确认请求拿到最终结果后清除 Key；
- 普通新问题或取消操作清除 Key，避免串用。

后端已有幂等测试证明：相同 Key 返回同一工单，不同 Key 返回 409。

## 4. SSE id 的作用

后端为每条进度和结果增加 `id: {session_id}:{sequence}`。当前不声称服务端事件回放，但协议已经具备事件序号，未来可以在此基础上增加 `Last-Event-ID` 重放。

## 5. 代码入口

- `frontend/src/api.ts`：`streamAgent` 接受 `AbortSignal`；
- `frontend/src/App.tsx`：停止、重试、确认 Key 生命周期；
- `src/support_pilot/api/routes.py`：SSE 事件 id；
- `tests/integration/test_agent_api.py`：SSE id 测试；
- 前端测试：signal 透传、停止后重试。

## 6. 验收结果

- 后端完整测试：114 passed；
- 前端：6 项单元测试、lint、build 通过；
- Chromium E2E：1 passed；
- 同 Key 工单重放和不同 Key 409：既有集成测试通过；
- 未引入新依赖，未改变 Alembic 业务模型。

## 7. 面试时怎么讲

“我把浏览器中止和服务端取消区分开。用户停止等待后，界面提示服务器可能已完成；重试确认会复用同一个幂等键，避免重复工单。后端 SSE 增加事件 id，为后续真正的断线重放留下协议基础。节点级 PostgresSaver 我评估过，但因为它会带来非 Alembic 管理表和依赖源改写，当前没有为了技术名词盲目引入。”
