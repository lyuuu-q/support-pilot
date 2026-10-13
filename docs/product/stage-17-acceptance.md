# 第十七阶段：Cookie 会话与 CSRF 防护验收

状态：已实现 HttpOnly Cookie 会话、CSRF 双提交、刷新轮换与登出撤销
验证日期：2026-10-13

## 1. 交付范围

- [x] `auth_sessions` 表与迁移 0012；
- [x] 会话服务（创建/查找/轮换/撤销/CSRF 校验）；
- [x] 访问令牌 `sid` 绑定与 Cookie 路径会话校验；
- [x] 登录、刷新、登出接口与 Cookie 读写；
- [x] 依赖层 Cookie 认证 + 写操作 CSRF 校验 + 审计；
- [x] 前端去掉 localStorage，改为凭证自动携带；
- [x] 脚本/demo 显式使用 token 模式；
- [x] 集成、前端与浏览器测试；
- [x] ADR、评测、学习文档。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S17-AC-01 | 登录响应不含访问令牌，Cookie 属性正确 | `test_cookie_login_keeps_tokens_out_of_javascript_and_authenticates_requests` |
| S17-AC-02 | 无/错误 CSRF 头的写操作被 403 拒绝 | `test_cookie_session_requires_csrf_header_for_writes` |
| S17-AC-03 | refresh 轮换后旧令牌重放 401 | `test_refresh_rotates_the_token_and_rejects_replay` |
| S17-AC-04 | 登出后旧访问令牌 401 且记录审计 | `test_logout_revokes_the_session_and_clears_cookies` |
| S17-AC-05 | token 模式仍可用于脚本 | `test_token_mode_still_issues_bearer_tokens_for_scripts` |
| S17-AC-06 | 前端不保存令牌且写请求带 CSRF 头 | `frontend/src/api.test.ts` |
| S17-AC-07 | 无会话时回退登录页并可登录 | `frontend/src/App.test.tsx` |
| S17-AC-08 | 浏览器完整业务闭环 | Playwright Chromium 用例 |
| S17-AC-09 | 迁移无漂移 | `uv run alembic check` |

## 3. 结果

- 后端完整测试：127 passed（新增 5）；
- 前端：13 项单测、lint、生产构建通过；
- 浏览器端到端：1 passed；
- Ruff、Mypy、`alembic check` 通过。

## 4. 边界

- `SameSite=Lax` + 双提交是纵深防御，不是 CSRF 的形式化证明；
- 本地 HTTP 使用 `auth_cookie_secure=false`，生产 HTTPS 必须置 true；
- 未实现设备列表、撤销全部会话、并发 refresh 竞态收敛；
- 未接入 OIDC/单点登录；
- Bearer 兼容路径不做 CSRF 校验（无 Cookie 即无跨站提交面）；
- 会话表暂无保留期清理。
