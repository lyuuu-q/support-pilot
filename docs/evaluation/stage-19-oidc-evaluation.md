# 第十九阶段评测：OIDC 登录

- 运行时间：2026-10-14（Asia/Shanghai）
- 数据库：PostgreSQL 16 + pgvector（localhost:54329 / 54330，已应用迁移 0013）
- 数据性质：合成账号；IdP 为本地开发用实现，不是生产身份系统
- 浏览器：Playwright 自带 Chromium v1243（与 CI 一致）

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff | 通过 |
| Mypy | 60 个源码文件无问题 |
| 后端完整测试 | 149 passed（新增 13 项 OIDC） |
| 前端单测 | 16 passed |
| 前端 lint / 生产构建 | 通过（JS gzip 66.0 kB） |
| 浏览器端到端 | 2 passed（企业登录闭环 3.4s + 工单闭环 5.2s） |
| `alembic upgrade head` + `alembic check` | 通过，无模型漂移 |

## 授权码流程（假 IdP，真实 RSA 签名）

| 场景 | 结果 |
|---|---|
| 授权请求参数 | `response_type=code`、`scope=openid profile email`、`code_challenge_method=S256`、43 字符 challenge |
| 数据库中的 state | 只存 SHA-256 哈希，明文不回存 |
| 授权码交换 | 假 IdP 用收到的 `code_verifier` 重算摘要并与 challenge 比对通过 |
| 回调结果 | 302 到 `/`，下发访问/刷新（HttpOnly）与 CSRF（可读）Cookie |
| 随后 `/auth/me` | 200，返回绑定的本地账号 |
| 身份绑定 | 写入 `user_identities`（issuer + subject） |
| 审计 | 记录 `oidc_login` |
| 流程记录 | `consumed_at` 已写入（一次性） |
| state 重放 | 400 `oidc_flow_failed` |
| 陌生邮箱 | 403 `oidc_account_not_linked`，且未创建任何绑定 |

## ID Token 校验

| 场景 | 结果 |
|---|---|
| 合法令牌（含大小写混合邮箱） | 通过，邮箱归一化为小写 |
| nonce 不符 | 拒绝 |
| 受众错误 | 拒绝 |
| 已过期 | 拒绝 |
| `email_verified=false` | 拒绝 |
| 签名被篡改 | 拒绝 |
| 未知 `kid` | 拒绝 |
| HS256（用公钥材料作 HMAC 密钥） | 拒绝（算法白名单先于验签） |

## 浏览器闭环

点击"使用企业账号登录" → 跳转本地 IdP（127.0.0.1:18002）→ 提交合成账号 → 回到控制台并显示 `Alpha Admin（合成用户）`。同时断言：

- `window.localStorage` 为空（页面不保存任何令牌）；
- `support_pilot_access` Cookie 为 HttpOnly；
- `support_pilot_csrf` Cookie 非 HttpOnly（前端需要读取）。

## 环境限制与处理

- 离线环境无法执行 `uv lock` 重新解析依赖（缓存缺少其他平台/解释器版本的产物）。`pyjwt` 改为 `pyjwt[crypto]` 后，按 uv 生成格式手工更新了 `uv.lock` 中该依赖的 extras 元数据；`uv sync --frozen --offline --dry-run` 可正常读取该锁文件。联网环境下重跑 `uv lock` 应无差异。
- 未对真实 IdP 联调：`cdn`/外部网络受限，且本阶段目标是客户端侧正确性。接入真实 IdP 时需要复核 issuer、redirect_uri 白名单与客户端认证方式。

## 边界

- 合成账号与本地 IdP，不代表生产身份治理能力；
- 无 RP-initiated logout、令牌撤销/刷新、JIT 建号、角色映射与 MFA；
- 每次登录实时拉取 discovery 与 JWKS，无缓存；
- 同时只支持一个 IdP。
