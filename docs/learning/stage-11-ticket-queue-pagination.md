# 第十一阶段学习说明：工单队列游标分页

## 为什么要从 offset 改为 cursor

offset 的问题不是“慢”这么简单，而是持续变化的队列里会漂移：用户看第一页时新增或删除了工单，第二页可能重复或漏项。游标把排序字段和最后一条记录编码进响应，下一页从“这条之后”继续，语义更稳定。

## 游标为什么用 created_at + id

只按 created_at 排序时，两条工单时间相同会导致顺序不稳定。增加 id 作为第二排序键，保证即使时间相同也有确定顺序。游标同时保存两者，查询条件写成：

`created_at < cursor_time OR (created_at = cursor_time AND id < cursor_id)`

## 如何判断还有下一页

服务端查询 `limit + 1` 条。返回时只展示 limit 条；如果实际拿到了 limit+1 条，说明还有下一页，`next_cursor` 取当前页最后一条。

## 为什么保留 offset

旧调用可能还在使用 offset。保留它可以兼容，但要求不能和 cursor 同时使用，否则服务端无法判断到底按哪个语义分页。

## 搜索和状态筛选

- 搜索匹配 `public_code`、`summary`、`description`；
- LIKE 通配符会转义，避免用户输入 `%` 改变搜索语义；
- 当前使用 `ilike`，规模变大时需要 pg_trgm 或全文索引；
- 状态筛选由服务端完成，前端不下载全部工单再过滤。

## 验收结果

- 后端票务集成测试：通过；
- 两页、搜索、状态筛选、无效游标、cursor+offset 冲突：通过；
- 前端：lint、7 项单元测试、build 通过；
- Chromium E2E：1 passed。
