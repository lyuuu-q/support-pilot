# 第十八阶段：会话生命周期与清理验收

状态：已实现会话列表、单个撤销、全部撤销与会话保留清理
验证日期：2026-10-14

## 1. 交付范围

- [x] `auth_session_retention_days` / `auth_session_prune_batch_size` 配置；
- [x] `prune_auth_sessions`（dry-run 默认、只看 expires_at）；
- [x] `GET /auth/sessions`、`POST /auth/sessions/{id}/revoke`、`POST /auth/logout-all`；
- [x] 审计事件与三个会话指标、`auth.sessions.prune` Span；
- [x] `scripts/prune_auth_sessions.py` 与维护脚本两段式执行；
- [x] 前端"登出所有设备"入口；
- [x] 集成 / 清理 / 观测 / 前端 / 浏览器测试；
- [x] ADR、评测、学习文档。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S18-AC-01 | 列出活跃会话并标记当前会话 | `test_list_sessions_marks_the_current_browser_session` |
| S18-AC-02 | 撤销其他会话后当前会话仍可用，被撤销会话 401 | `test_revoke_one_session_keeps_the_current_session_working` |
| S18-AC-03 | 跨账号撤销返回 404 | `test_cannot_revoke_another_users_session` |
| S18-AC-04 | 缺少 CSRF 头被 403 拒绝 | `test_session_revocation_requires_csrf_header` |
| S18-AC-05 | 全部撤销后所有会话失效并清 Cookie、写审计 | `test_logout_all_revokes_every_session_and_clears_cookies` |
| S18-AC-06 | dry-run 报告但不删除 | `test_dry_run_reports_without_deleting` |
| S18-AC-07 | 只清理 cutoff 前过期会话，保留活跃/已撤销未过期会话 | `test_prune_deletes_only_sessions_expired_before_cutoff` |
| S18-AC-08 | 批量上限生效 | `test_prune_respects_the_batch_limit` |
| S18-AC-09 | 会话指标与清理 Span 可采集 | `test_auth_session_events_emit_spans_and_metrics` |
| S18-AC-10 | 前端可一键登出所有设备 | `frontend/src/App.test.tsx` |
| S18-AC-11 | 维护脚本一次执行两段清理 | `scripts/run_maintenance.ps1` 实跑输出 |

## 3. 结果

- 后端完整测试：136 passed（新增 9）；
- 前端：14 项单测、lint、构建通过；
- 浏览器端到端：1 passed；
- 维护脚本 dry-run：Agent 历史与会话两段均输出 0 删除；
- Ruff、Mypy（59 文件）通过。

## 4. 边界

- 只展示活跃会话，无历史会话、IP 与设备指纹；
- 没有"保留当前、撤销其他"语义与活跃会话数量上限；
- 清理仍需部署方创建计划任务，本阶段未自动调度；
- 会话保留期小于 refresh 有效期时会提前失效，属刻意取舍；
- 指标为本地合成流量结果，不代表生产规模。
