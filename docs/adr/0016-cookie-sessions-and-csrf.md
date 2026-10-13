# ADR 0016：浏览器 Cookie 会话、CSRF 与刷新轮换

- 状态：Accepted
- 日期：2026-10-13

## 背景

第六阶段的前端把 Bearer 令牌存进 `localStorage`：任何注入脚本都能直接读走，且令牌在有效期内无法即时撤销。P3 要求"令牌不暴露给页面 JavaScript"，并提供可撤销的会话。

## 决策

1. 登录默认进入 Cookie 模式，响应只返回身份、CSRF 令牌和有效期，不再把访问令牌交给页面：
   - `support_pilot_access`：HttpOnly、`Path=/`、`SameSite=Lax`，有效期与 `jwt_access_token_minutes` 一致；
   - `support_pilot_refresh`：HttpOnly、`Path=/api/v1/auth`、14 天；
   - `support_pilot_csrf`：**故意可被 JS 读取**，用于双提交校验。
2. 访问令牌新增 `sid` 声明绑定 `auth_sessions` 行。Cookie 认证时校验会话 `status='active'` 且未过期，因此登出与撤销对访问令牌立即生效，而不是等 30 分钟过期。
3. 写操作（POST/PUT/PATCH/DELETE）在 Cookie 认证下必须同时满足：
   - `X-CSRF-Token` 请求头等于 `support_pilot_csrf` Cookie 值（双提交，跨站脚本读不到同源 Cookie）；
   - 该值的哈希等于会话行 `csrf_hash`（绑定校验）。
   任一条不满足返回 403 `csrf_token_invalid` 并写审计事件。
4. refresh 采用轮换：旧令牌立刻置为 `revoked`，新会话通过 `rotated_from` 记录来源；重放旧令牌返回 401。
5. 保留 `session_mode="token"` 与非浏览器路径：命令行脚本、集成测试和 API 客户端可以显式索取 Bearer 令牌（不需要 CSRF）。浏览器端不使用该模式。
6. 前端不再保存任何令牌：所有请求 `credentials: 'include'`，写请求自动附带 CSRF 头；启动时先试 `/auth/me`，401 再试一次 `/auth/refresh`，两者都失败才显示登录页。
7. 新增配置：Cookie 名、CSRF 头名、refresh Cookie 路径、`auth_cookie_secure`、`auth_refresh_token_days`。

## 代价与限制

- `SameSite=Lax` + 双提交是纵深防御，不是 CSRF 的完整证明；本地 HTTP 下 `auth_cookie_secure=false`，生产 HTTPS 必须置为 `true`；
- 未实现设备列表、"撤销全部会话"、refresh 会话上限与 IP 记录；OIDC/单点登录仍未接入；
- 同一 refresh 令牌并发刷新时只有一个成功，另一个得到 401，前端按"重新登录"处理，没有做竞态收敛；
- Bearer 客户端不经过 CSRF 校验，这是刻意的（无 Cookie 就没有跨站提交面），但也意味着兼容路径的令牌仍需自行保管；
- 会话表随登录次数增长，本阶段没有加入会话清理（沿用第十五阶段的清理思路，留待后续）。

## 验证方式

- 集成测试：Cookie 属性与令牌不外泄、无 CSRF 头写操作 403、refresh 轮换与重放 401、登出后旧访问令牌 401 且写审计、`session_mode="token"` 仍可用；
- 前端单测 13 项、lint、生产构建通过；
- 1 条浏览器端到端（登录 → SSE 引用回答 → 确认工单 → 登出 → 支持人员认领并推进）通过；
- 后端完整测试 127 项、Ruff、Mypy、`alembic check` 通过。
