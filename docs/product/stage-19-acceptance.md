# 第十九阶段：OIDC 登录与身份绑定验收

状态：已实现 OIDC 授权码 + PKCE 登录、按已验证邮箱绑定既有账号、Cookie 会话复用
验证日期：2026-10-14

## 1. 交付范围

- [x] `oidc_login_requests`、`user_identities` 表与迁移 0013；
- [x] discovery、授权 URL（state/nonce/PKCE S256）、授权码交换、ID Token 校验；
- [x] `GET /auth/providers`、`GET /auth/oidc/start`、`GET /auth/oidc/callback`；
- [x] 按已验证邮箱绑定，禁止隐式建号（403 + 审计）；
- [x] 成功后签发本项目 Cookie 会话并记录 `oidc_login` 审计；
- [x] 前端"使用企业账号登录"入口（仅当 API 声明启用）；
- [x] 开发用 IdP 脚本与浏览器端到端用例；
- [x] `pyjwt[crypto]` 依赖与锁文件；
- [x] ADR、评测、学习文档。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S19-AC-01 | 授权码流程建立 Cookie 会话并绑定身份 | `test_authorization_code_flow_links_identity_and_issues_cookie_session` |
| S19-AC-02 | 授权请求包含 state/nonce/PKCE S256 且只存 state 哈希 | 同上 |
| S19-AC-03 | PKCE verifier 被 IdP 校验通过 | 同上（假 IdP 重算摘要） |
| S19-AC-04 | state 重放被拒 | `test_authorization_code_flow_rejects_state_replay` |
| S19-AC-05 | 陌生邮箱 403 且不建号 | `test_unknown_email_is_not_provisioned_implicitly` |
| S19-AC-06 | 7 类非法 ID Token 全部被拒 | `test_id_token_verification_rejects_invalid_tokens` |
| S19-AC-07 | 合法令牌解析出身份并归一化邮箱 | `test_id_token_verification_accepts_a_valid_token` |
| S19-AC-08 | providers 端点按开关广告能力 | `test_provider_endpoint_advertises_oidc_only_when_enabled` |
| S19-AC-09 | 前端仅在启用时显示企业登录入口 | `frontend/src/App.test.tsx` |
| S19-AC-10 | 浏览器真实跳转闭环，页面无令牌可读 | `frontend/e2e/oidc-login.spec.ts` |
| S19-AC-11 | 迁移无漂移 | `uv run alembic check` |

## 3. 结果

- 后端完整测试：149 passed（新增 13）；
- 前端：16 项单测、lint、构建通过；
- 浏览器端到端：2 passed；
- Ruff、Mypy（60 文件）、`alembic check` 通过；
- 开发用 IdP 与 API 均按 Runbook 步骤实际启动验证。

## 4. 边界

- 未与任何真实 IdP 联调，只有本地开发 IdP 与假 IdP 测试；
- 未实现 RP-initiated logout、IdP 令牌撤销/刷新、JIT 建号、角色映射、MFA；
- 每次登录实时拉取 discovery 与 JWKS，无缓存与退避；
- `nonce`/`code_verifier` 明文入库（单次使用 + 10 分钟过期）；
- 同时只支持一个 IdP；本地口令登录仍然保留。
