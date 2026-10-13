# 第十七阶段评测：Cookie 会话、CSRF 与刷新轮换

- 运行时间：2026-10-13（Asia/Shanghai）
- 数据库：PostgreSQL 16 + pgvector（localhost:54329 / 54330，已应用迁移 0012）
- 数据性质：合成用户与合成工单，不是生产流量
- 浏览器：Playwright 自带 Chromium v1243（与 CI 一致），缓存路径 `C:\Users\刘雨晴\Documents\github\.playwright-browsers`

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 58 个源码文件无问题 |
| 后端完整测试 | 127 passed（新增 5 项会话测试） |
| `alembic upgrade head` + `alembic check` | 通过，无模型漂移 |
| 前端单测 | 13 passed（原 10） |
| 前端 lint / 生产构建 | 通过（JS gzip 65.9 kB） |
| 浏览器端到端 | 1 passed（5.5s） |

## 会话行为验证

| 场景 | 结果 |
|---|---|
| 登录响应体 | 只有身份、CSRF 令牌、有效期；无访问令牌 |
| 访问/刷新 Cookie | 带 `HttpOnly`；刷新 Cookie 限定在 `/api/v1/auth` |
| CSRF Cookie | 不带 `HttpOnly`（前端需要读取） |
| 仅凭 Cookie 访问 `/auth/me`、`/tickets` | 200 |
| 写操作缺少 `X-CSRF-Token` | 403 `csrf_token_invalid` |
| 写操作 CSRF 头与 Cookie 不一致 | 403 `csrf_token_invalid` |
| 写操作带上正确 CSRF 头 | 200 |
| refresh 后旧刷新令牌重放 | 401 |
| refresh 后新访问 Cookie | 仍可访问 `/auth/me` |
| 登出后旧访问 Cookie | 401 |
| 登出后会话行 | `status=revoked`、`revoked_at` 非空、写入 `auth.session.revoke` 审计 |
| `session_mode="token"` | 返回 Bearer 令牌且不设置会话 Cookie |

## 浏览器端到端

用例覆盖：登录 → SSE 引用回答（`引用证据`、`逐条主张`）→ 客户确认创建工单 → 登出 → 支持人员登录 → 认领并推进到 `in_progress`。全程使用 Cookie 会话，页面 JavaScript 不接触任何令牌。

## 环境限制与处理

- README 里旧的浏览器缓存路径（`D:\model-cache`）在本机已不存在，直接运行会提示缺少 `chromium_headless_shell-1243`；
- 重新下载时 `cdn.playwright.dev` 对本机所在区域返回 403 `AccessDenied`（not available in your location），Chromium 与 ffmpeg 都拉不下来；
- 实际可用的浏览器缓存位于工作区内 `C:\Users\刘雨晴\Documents\github\.playwright-browsers`（含 `chromium_headless_shell-1243`、`chromium-1243`、`ffmpeg-1011`），通过 `PLAYWRIGHT_BROWSERS_PATH` 指向它即可运行，浏览器版本与 CI 一致；
- 兜底方案：无本地缓存时可设置 `E2E_BROWSER_CHANNEL=chrome`（或 `msedge`）改用系统浏览器，该通道下自动关闭录屏；
- 沙箱环境启动浏览器还需要额外授权，否则 Playwright 会静默挂起而不报错。

## 边界

- 合成数据、本机单实例，不代表生产会话规模或可用性；
- 未做并发 refresh 竞态、Cookie 大小限制、多标签页同步登出的专项验证；
- 未验证 HTTPS 下 `auth_cookie_secure=true` 的实际部署行为；
- Bearer 兼容路径不做 CSRF 校验，属于刻意设计而非遗漏。
