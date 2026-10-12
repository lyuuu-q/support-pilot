# 第十一阶段：工单队列分页与筛选验收

状态：已实现服务端游标分页、搜索、状态筛选和控制台加载更多
验证日期：2026-10-12

## 1. 交付范围

- [x] `created_at + id` 不透明游标；
- [x] `/tickets` 支持 `cursor`、`q`、`status`、`limit`；
- [x] `next_cursor` 返回和 `limit + 1` 余量判断；
- [x] 搜索 public_code、summary、description；
- [x] 状态筛选和租户隔离保持；
- [x] 复合索引迁移 `0007`；
- [x] React 控制台搜索框、状态筛选和“加载更多”。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S11-AC-01 | 两页无重复且合并等于全量 | `test_ticket_queue_supports_cursor_search_and_status_filter` |
| S11-AC-02 | public_code 搜索只返回目标工单 | 同上 |
| S11-AC-03 | 状态筛选只返回对应状态 | 同上 |
| S11-AC-04 | 无效游标返回 400 | 同上 |
| S11-AC-05 | cursor 与 offset 混用返回 400 | 同上 |
| S11-AC-06 | 前端查询参数正确 | `frontend/src/api.test.ts` |
| S11-AC-07 | 浏览器完整闭环不回归 | Chromium E2E 1 passed |

## 3. 边界

- 当前 `q` 使用 `ilike`，大表需要 pg_trgm 或全文索引；
- `total` 仍做精确计数，超大数据量需改为近似或独立统计；
- 只支持单状态筛选，暂不支持多状态和自定义排序；
- 前端筛选需要提交表单，不做输入即时搜索。
