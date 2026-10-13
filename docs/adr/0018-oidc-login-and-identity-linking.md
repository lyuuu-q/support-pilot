# ADR 0018：OIDC 登录与外部身份绑定

- 状态：Accepted
- 日期：2026-10-14

## 背景

路线图最后一项是"用 OIDC + 企业目录替换本地口令登录"。第十七、十八阶段已经把浏览器会话换成 HttpOnly Cookie 并支持撤销与清理，因此本阶段只需要解决"人怎么证明自己是谁"，其余会话机制可以原样复用。

真实 IdP（Keycloak/Auth0/企业微信）需要外部账号与网络，无法在本机验证。因此本阶段的决策是：**实现并完整验证 OIDC 客户端侧**，用一个本地开发用 IdP 承担"IdP 角色"，并把"未对真实 IdP 做过联调"如实写入边界。

## 决策

1. 认证方式为**授权码 + PKCE（S256）**，不使用隐式流；`state`、`nonce`、`code_verifier` 由服务端生成并保存。
2. 新增两张表（迁移 0013）：
   - `oidc_login_requests`：保存 `state_hash`（只存哈希）、`nonce`、`code_verifier`、`redirect_uri`、`expires_at`、`consumed_at`；
   - `user_identities`：`(issuer, subject) -> user_id` 绑定，唯一约束防止同一外部身份绑定到两个本地账号。
3. ID Token 校验规则：
   - 只接受非对称算法（RS256/384/512、ES256/384/512），**显式拒绝 HS256**，避免用公钥当 HMAC 密钥的算法混淆攻击；
   - 用 JWKS 按 `kid` 选键，验签后再校验 `iss`、`aud`、`exp`、`iat`、`nonce`；
   - 要求 `email` 存在且 `email_verified=true`。
4. 账号绑定规则：**只按已验证邮箱绑定到已存在的本地账号**，绝不隐式创建用户。找不到活跃本地账号时返回 403 `oidc_account_not_linked`，并写"登录被拒"审计。首次成功绑定会写入 `user_identities`。
5. 登录成功后**不保存 IdP 的令牌**：立即签发本项目自己的 Cookie 会话（复用第十七阶段的 `auth_sessions`），因此会话撤销、CSRF、保留清理全部沿用。
6. 本地口令登录保留（`POST /auth/login`），OIDC 是并行入口；`GET /api/v1/auth/providers` 告知前端有哪些方式可用，前端据此决定是否显示"使用企业账号登录"。
7. 提供 `scripts/dev_oidc_provider.py`：内存态、RS256、支持 PKCE 校验的**开发用 IdP**，用于本地演示与浏览器端到端测试。它明确不是产品的一部分，也不是生产 IdP。
8. 依赖：`pyjwt[crypto]`（RSA/EC 验签需要 `cryptography`）。

## 代价与限制

- 未与任何真实 IdP 联调（Keycloak/Auth0/企业微信等），只有本地开发 IdP 与假 IdP 测试；
- 不处理 IdP 侧登出（RP-initiated logout）、IdP 令牌撤销与刷新令牌：本项目只用自己的会话；
- 无 JIT 自动建号、无角色/用户组映射、无 MFA 策略；
- 每次登录都实时拉取 discovery 与 JWKS（便于处理轮换，但没有缓存与超时退避）；
- `oidc_login_requests` 保存的 `nonce` 与 `code_verifier` 是明文（单次使用、默认 10 分钟过期）；会话令牌则始终只存哈希；
- 同一时间只支持一个 IdP；
- 客户端密钥为可选（`client_secret_post`），未实现 `private_key_jwt`。

## 验证方式

- 假 IdP（httpx MockTransport + 真实 RSA 签名）覆盖：完整授权码流程、state 重放 400、陌生邮箱 403、7 类非法 ID Token（nonce 不符、受众不符、过期、邮箱未验证、签名被篡改、未知 kid、HS256 算法混淆）；
- 真实浏览器端到端：点击"使用企业账号登录" → 本地 IdP 登录 → 回到控制台，并断言 `localStorage` 为空、访问 Cookie 为 HttpOnly、CSRF Cookie 非 HttpOnly；
- 后端 149 项、前端 16 项测试通过，Ruff、Mypy、`alembic check` 通过。
