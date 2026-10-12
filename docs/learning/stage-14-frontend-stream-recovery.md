# 第十四阶段学习说明：前端断线自动恢复

## 为什么后端有回放，前端还要改

后端回放 API 只是能力；如果 UI 捕获错误后直接提示失败，用户仍然要重新提问。前端必须在事件流断开时保留 run id，然后主动回放和恢复。

## event id 为什么是关键

SSE `id: {run_id}:{sequence}` 同时给出两个信息：

- run id：恢复时应访问哪个运行；
- sequence：已经看到哪些事件。

前端保存最后一个 event id，网络错误后就能定位对应 run，不需要依赖额外状态。

## 恢复流程

1. streamAgent 回调 event id；
2. 网络错误且 run id 存在；
3. 调用事件回放 API，恢复 progress Trace；
4. 若已有 result，直接显示结果；
5. 若没有 result，调用 checkpoint 恢复 API；
6. 成功后提示“已从服务端恢复断线前的事件”。

## 主动中止和网络错误的区别

- AbortError：用户主动点击停止，保留“停止等待/重试”语义；
- 其他网络错误：自动恢复，不要求重新提交。

## 当前限制

回放和恢复是两个 HTTP 请求，不是单条自动续传的 SSE；事件保留、清理和游标分页仍是后续工作。

## 验收结果

- 前端单元测试：10 passed；
- API event id、回放参数、恢复 POST：通过；
- UI 网络中断恢复：通过；
- Chromium E2E：1 passed。
