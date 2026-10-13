# 第十九阶段学习说明：OIDC 登录

## 为什么用授权码 + PKCE，而不是"让前端拿令牌"

历史上 OAuth 的隐式流把令牌直接放在 URL 片段里交给浏览器，任何能被注入的脚本都能读到。授权码流把"码"交给浏览器、"令牌"留在后端，PKCE 再补上"换令牌的人必须是最先发起登录的人"：

1. 服务端生成随机 `code_verifier`，把它的 SHA-256 摘要（`code_challenge`）随授权请求发出；
2. IdP 回调时返回一次性 `code`；
3. 服务端用 `code` + 原始 `code_verifier` 换令牌；
4. IdP 重新计算摘要比对，不一致就拒绝。

这样即使有人截获了回调 URL 上的 `code`，没有原始 verifier 也换不到令牌。

## state、nonce 各自防什么

| 参数 | 防的攻击 | 校验方式 |
|---|---|---|
| `state` | CSRF / 把攻击者的授权码塞进受害者的浏览器 | 只保存哈希，回调时查表并立刻标记已用（一次性） |
| `nonce` | ID Token 重放（旧令牌被拿来当新登录） | 生成的 nonce 与会话绑定，校验 ID Token 里的 `nonce` 完全一致 |

两者都放在流程记录里（`oidc_login_requests`），默认 10 分钟过期。`state` 只存哈希，和会话令牌的处理一致——数据库被读走也不能直接拿来回放。

## 为什么必须拒绝 HS256

ID Token 用非对称密钥签名，公钥是公开的。如果校验方"按令牌头部声明的算法决定怎么验"，攻击者可以把令牌头改成 `HS256`，然后用**公钥文本当 HMAC 密钥**重新签名；校验方若照做就会验签通过——这就是算法混淆。防御很直接：先检查算法在白名单内（只允许非对称），再选键验签。本阶段用一条测试专门覆盖这个场景。

## 为什么只按已验证邮箱绑定、绝不自动建号

自动建号意味着"任何一个 IdP 用户都能变成 SupportPilot 用户"，权限模型会被绕过。这里的规则是：

- `email_verified` 必须为真；
- 邮箱必须匹配一个**已存在且活跃**的本地账号；
- 匹配成功后写入 `(issuer, subject) -> user_id` 绑定，之后登录按 `sub` 走，邮箱改名不影响；
- 匹配不到就 403 `oidc_account_not_linked`，并写"被拒"审计。

代价是运维需要提前建号；收益是身份来源收敛、权限不会被意外放大。这是刻意取舍，不是遗漏。

## 为什么登录成功后丢掉 IdP 的令牌

拿到了 ID Token 就完成了"你是谁"，没必要继续持有 IdP 的访问令牌——留着只会扩大泄露面，还得处理 IdP 侧的刷新与撤销。所以流程结束后立即签发**本项目自己的** Cookie 会话：撤销、CSRF、保留清理这些能力已经在第十七、十八阶段做好，直接复用。

## 开发用 IdP 是什么、不是什么

`scripts/dev_oidc_provider.py` 是一个内存态的迷你 IdP：启动时生成 RSA 密钥，提供 discovery、JWKS、授权页、PKCE 校验的令牌端点，只认三个合成账号。它让"点按钮 → 跳转 → 回来"整条链路可以在本机被真实浏览器验证。

它**不是**产品的一部分，也不是生产 IdP。没有与 Keycloak/Auth0/企业微信做过联调，这也是本阶段最大的诚实边界。

## 本地怎么试

```powershell
# 终端 1：开发用 IdP
uv run python scripts/dev_oidc_provider.py

# 终端 2：启用 OIDC 的 API
$env:SUPPORT_PILOT_OIDC_ENABLED = 'true'
$env:SUPPORT_PILOT_OIDC_ISSUER = 'http://127.0.0.1:18002'
$env:SUPPORT_PILOT_OIDC_CLIENT_ID = 'support-pilot-console'
$env:SUPPORT_PILOT_OIDC_REDIRECT_URI = 'http://127.0.0.1:8000/api/v1/auth/oidc/callback'
uv run uvicorn support_pilot.main:app --reload
```

浏览器打开控制台即可看到"使用企业账号登录"，合成账号密码与演示口令相同。

## 验收结果

- 后端 149 项测试通过（新增 13 项 OIDC）；
- 前端 16 项单测、lint、构建通过；
- 浏览器端到端 2 条通过（企业登录闭环 + 原有工单闭环）；
- 算法混淆、nonce/受众/过期/未验证邮箱/篡改签名/未知 kid 全部被拒。
