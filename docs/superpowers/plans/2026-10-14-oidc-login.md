# OIDC 登录与身份绑定执行计划

**目标：** 用标准 OIDC 授权码流程接入企业身份，同时复用已有 Cookie 会话与撤销能力。
**ADR：** `docs/adr/0018-oidc-login-and-identity-linking.md`

## 步骤

- [x] `oidc_login_requests` 与 `user_identities` 表、迁移 0013；
- [x] OIDC 客户端：discovery、授权 URL（state/nonce/PKCE）、授权码交换、ID Token 校验；
- [x] `GET /auth/providers`、`GET /auth/oidc/start`、`GET /auth/oidc/callback`；
- [x] 按已验证邮箱绑定既有账号，禁止隐式建号；
- [x] 登录成功后签发本项目 Cookie 会话并写审计；
- [x] 前端"使用企业账号登录"入口；
- [x] 开发用 IdP 脚本与浏览器端到端用例；
- [x] 假 IdP 集成测试（流程、重放、陌生邮箱、7 类非法令牌）；
- [x] 依赖声明与锁文件更新；
- [x] ADR、评测、验收、学习文档。

## 完成定义

- [x] 只接受非对称签名算法，HS256 算法混淆被拒绝；
- [x] nonce/iss/aud/exp 校验失败都拒绝登录；
- [x] 未验证邮箱不得用于绑定；
- [x] 陌生邮箱返回 403 且不建号；
- [x] state 一次性，重放返回 400；
- [x] 浏览器完整跳转闭环通过且页面无令牌可读；
- [x] 全量后端、前端、浏览器测试通过。
