# 第十四阶段：前端 SSE 断线恢复验收

状态：已实现浏览器自动回放事件并恢复 checkpoint 运行
验证日期：2026-10-12

## 1. 交付范围

- [x] streamAgent 回调 SSE event id；
- [x] 保存 run id 和最后事件 id；
- [x] 网络错误自动回放事件；
- [x] 有 result 时直接恢复结果；
- [x] 无 result 时调用恢复 API；
- [x] 恢复成功后显示提示；
- [x] 主动中止保持原语义。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S14-AC-01 | event id 回调 | `frontend/src/api.test.ts` |
| S14-AC-02 | 回放参数正确 | 同上 |
| S14-AC-03 | 恢复 POST 正确 | 同上 |
| S14-AC-04 | 网络中断后恢复 Trace | `frontend/src/App.test.tsx` |
| S14-AC-05 | 恢复最终回答 | 同上 |
| S14-AC-06 | 完整闭环不回归 | Chromium E2E |

## 3. 结果

- 前端单元测试：10 passed；
- lint/build：通过；
- Chromium E2E：1 passed；
- 后端 118 项测试不回归。

## 4. 边界

- 回放和恢复不是单条长连接续传；
- 事件分页上限 500；
- 清理和保留期限未实现。
