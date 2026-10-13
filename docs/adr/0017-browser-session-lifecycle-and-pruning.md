# ADR 0017：浏览器会话的生命周期管理与清理

- 状态：Accepted
- 日期：2026-10-14

## 背景

第十六阶段给 Agent 历史加了保留清理，第十七阶段引入了 `auth_sessions` 会话表，但当时明确把两件事留作后续：会话表会随登录次数无限增长；用户也无法看到或撤销自己的其他会话。ADR 0016 把这两条写进了"代价与限制"，本阶段把它们补上。

## 决策

1. 会话可见与可撤销（仅限本人）：
   - `GET /api/v1/auth/sessions` 列出当前账号**活跃且未过期**的会话，标记哪一个是本次请求使用的会话；
   - `POST /api/v1/auth/sessions/{id}/revoke` 撤销指定会话；不属于调用者或已失效时返回 404，避免泄露他人会话是否存在；撤销的若是当前会话，同时清除 Cookie；
   - `POST /api/v1/auth/logout-all` 撤销该账号全部活跃会话并清除 Cookie。
2. 三个写接口都走 Cookie 认证 + CSRF 双提交，并写审计事件（`auth.session.revoke` / `auth.session.revoke_all`）。
3. 保留清理：
   - 新增 `auth_session_retention_days`（默认 30）与 `auth_session_prune_batch_size`（默认 500）；
   - `prune_auth_sessions` 只删除 `expires_at < cutoff` 的行，cutoff 为 `now - retention_days`。因此**活跃会话永远不可能被选中**，状态是 `active` 还是 `revoked` 不影响判定；
   - 默认 dry-run，真实删除需要显式 `--dry-run` 之外的方式（脚本默认 dry-run，`run_maintenance.ps1 -Execute` 才执行）。
4. 维护脚本：新增 `scripts/prune_auth_sessions.py`，并把 `scripts/run_maintenance.ps1` 改为依次执行 Agent 历史与会话两段清理，输出与日志合并。
5. 观测：`support_pilot.auth.sessions_started`、`sessions_revoked`（带 reason 标签）、`sessions_pruned`（带 dry_run 标签）三个计数指标，以及 `auth.sessions.prune` Span。
6. 前端只增加一个"登出所有设备"入口；设备列表 API 已具备，但控制台暂不做会话管理面板。

## 代价与限制

- 会话列表只返回活跃会话，不展示历史（已撤销/已过期）会话，也不记录 IP 与设备指纹；
- 撤销粒度是单会话或全量，没有"保留当前会话并撤销其他"的语义（前端可通过列表逐个撤销实现）；
- 清理是批处理脚本，仍然依赖部署方创建计划任务；本阶段没有自动调度；
- 会话保留期与 refresh 有效期相互独立：若保留期小于 refresh 有效期，长期不用的会话会先被删掉（等价于提前失效），这是刻意的保守取舍；
- 未实现"登录上限"（同一账号最多 N 个活跃会话）。

## 验证方式

- 集成测试：列表与当前会话标记、撤销单个会话后该会话失效而当前会话可用、跨账号撤销返回 404、缺少 CSRF 头被 403 拒绝、`logout-all` 撤销全部并清 Cookie 且写审计；
- 清理测试：dry-run 不删除、只删除 cutoff 之前过期的会话、被撤销但仍未过期的会话必须保留、批量上限生效；
- 观测测试：三个会话指标与 `auth.sessions.prune` Span 均可采集；
- 维护脚本 dry-run 输出两段 JSON；后端 136 项、前端 14 项、浏览器端到端 1 条通过。
