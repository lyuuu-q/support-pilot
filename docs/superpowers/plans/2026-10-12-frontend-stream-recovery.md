# 前端 SSE 断线自动恢复执行计划

**目标：** 浏览器流中断后自动回放事件并继续 checkpoint 运行，无需用户重新提问。
**ADR：** `docs/adr/0013-frontend-stream-recovery.md`

## 步骤

- [x] streamAgent 解析 SSE id 并回调；
- [x] 增加 listRunEvents 和 resumeAgentRun；
- [x] CustomerWorkspace 保存 run id 和最后事件 id；
- [x] 网络错误时自动回放/恢复；
- [x] 恢复成功后显示状态提示；
- [x] 覆盖 API 和 UI 测试；
- [x] 运行 lint、单测、build 和 E2E。

## 完成定义

- [x] 流中断不会要求用户重新提交；
- [x] progress Trace 能恢复；
- [x] 最终结果能恢复；
- [x] 用户主动中止语义不变；
- [x] 前后端全部回归通过。
