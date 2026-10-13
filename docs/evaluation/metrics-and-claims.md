# SupportPilot 指标口径与证据索引

## 项目定位

个人项目｜企业 SaaS 技术支持与智能工单 Agent｜合成数据与公开模型，非生产环境交付。

技术栈：Python、FastAPI、LangGraph、PostgreSQL、pgvector、SQLAlchemy、Alembic、React、TypeScript、Vite、JWT/RBAC、OpenTelemetry、Docker Compose、GitHub Actions。

## 项目要点

**SupportPilot｜企业 SaaS 技术支持与智能工单 Agent（个人项目）**

- 设计并实现 Provider 中立的 LangGraph 支持工作流，将意图/风险识别、混合 RAG、确定性业务工具、Answerability Gate、显式工单确认与人工接管串成可持久化闭环；用同文档/同主题/同版本的受控多证据门控解决跨 chunk 问题，80 条人工标注合成场景（91 个请求步骤）全部通过，重复副作用与高风险误执行均为 0。
- 基于 PostgreSQL/pgvector 实现关键词与向量双路召回、RRF、BGE Reranker、元数据过滤和 chunk 级引用；拆分 60 条 calibration 与 30 条冻结后 holdout，本地 BGE 在 holdout 上的 Recall@5 1.000、MRR 0.975、nDCG@5 0.982、Answerability F1 0.974，无答案误放行为 0。
- 构建 JWT/RBAC、多租户隔离、工单状态机、事务/幂等/乐观锁与审计，使用 React + SSE 展示真实节点 Trace、引用和人工处理；121 个后端测试覆盖率 93%，10 个前端单元测试及 1 条 Chromium 业务 E2E 通过，CI 还验证 Compose 构建、启动和前端反向代理探活。
- 将 RAG 证据粒度从 chunk 降到 claim，使用确定性 verifier 校验原文支持和技术标识，在 React 控制台两级展示 claim 与 chunk 引用，并在独立 faithfulness v2 数据集上跟踪覆盖率、支持率、引用精度和难负例误答率。
- 支持浏览器中止 SSE 等待，并在重试确认时复用同一幂等键；后端 SSE 增加事件 id，为后续服务端事件回放保留协议基础。
- 工单队列使用 created_at + id 不透明游标，支持状态筛选和工单号/摘要搜索，前端按需加载更多。
- Agent 运行使用 PostgresSaver 保存节点级 checkpoint，支持 interrupted 运行恢复；延迟从约 46ms 提升到约 700ms。
- SSE progress/result 事件按 run_id + sequence 持久化，所有者可通过回放 API 读取断线前事件，为 Last-Event-ID 续传提供基础。
- 前端在 SSE 网络中断后自动回放已发生事件并调用 checkpoint 恢复接口，无需用户重新提交。
- 恢复使用 PostgreSQL 行锁和 resuming 状态防止并发重复执行；提供带 dry-run 的历史清理脚本，保留活跃运行及其事件。
- 登录支持标准 OIDC 授权码 + PKCE：只接受非对称签名算法、校验 state/nonce/iss/aud/exp 与 `email_verified`，按已验证邮箱绑定既有账号且不隐式建号。
- 浏览器会话可列出、可单个撤销、可一键全部撤销，并按保留期清理过期行（活跃会话在判定上永不被选中）。
- 浏览器端改用 HttpOnly Cookie 会话并通过 `X-CSRF-Token` 双提交防御 CSRF；访问令牌绑定会话行，登出与 refresh 轮换后可即时撤销。
- 在 OTLP Trace 之外增加 Metrics：Agent、RAG 与历史清理产生有界标签的 counter/histogram，并提供 Compose `observability` profile 的 Collector（当前仅 debug exporter）与默认 dry-run 的维护脚本。

## 指标证据索引

| 指标口径 | 证据 | 限制 |
|---|---|---|
| 80/80 Agent 场景 | `docs/evaluation/results/agent-scenarios-v1-checkpoint.json` | 确定性 Provider、合成场景 |
| Intent macro-F1 1.000 | 同上，91 个带标签步骤 | 不代表 Qwen 泛化质量 |
| local BGE holdout Recall@5 1.000 / Gate F1 0.974 | `docs/evaluation/results/retrieval-holdout-local-bge-v1.json` | 30 条独立 ID 合成样本，仍非生产数据 |
| calibration 四项 1.000 | `docs/evaluation/stage-3-rag-evaluation.md` | 60 条同源合成样本，仅作校准/回归 |
| Qwen 7/7 冒烟 | `docs/evaluation/stage-4-qwen-smoke-evaluation.md` | 仅 7 条、调用 5 次 |
| 0 重复副作用/高风险误执行 | Agent 机器报告 + PostgreSQL 并发测试 | 非生产流量 |
| 121 tests / 93% | 2026-10-12 P0+P1a+P2+P1b+P1c+P1d 全量 pytest 记录 | local BGE 文件未计入常规覆盖 |
| 7 frontend tests | Vitest + Testing Library | jsdom 单元/组件层 |
| 1 browser E2E | Playwright Chromium：客户提问到人工处理 | deterministic Provider、单浏览器、隔离测试库 |
| claim support 1.000 / false answer 0.000 / coverage 0.8333 | `docs/evaluation/results/faithfulness-deterministic-v1.json` | 12 条合成问题，3 个 required claim 覆盖缺口，非生产忠实度 |
| checkpoint 80/80 / p50 698ms | `docs/evaluation/results/agent-scenarios-v1-checkpoint.json` | deterministic、本地单机，延迟换可恢复性 |
| SSE 回放 sequence 连续 / 越权 404 | `docs/evaluation/stage-13-sse-event-replay-evaluation.md` | 服务端回放，前端自动续传未实现 |
| Compose runtime | `main@7007b49` container job | CI runner 短时启动与探活，不代表生产稳定性 |
| 122 tests | 2026-10-13 全量 pytest 记录 | 新增观测与清理测试，仍为合成数据 |
| Agent/RAG Span 与指标 | `tests/integration/test_observability.py` | InMemory exporter，非生产流量 |
| Collector 40 spans / 10 metrics | 本机 otel-collector debug 日志 | 仅 debug exporter，无持久化或查询后端 |
| 127 tests | 2026-10-13 全量 pytest 记录 | 含 5 项 Cookie/CSRF 会话测试，合成数据 |
| Cookie 会话与 CSRF | `tests/integration/test_auth_session_api.py` | 本地 HTTP、`auth_cookie_secure=false`，非 HTTPS 部署验证 |
| 浏览器 E2E（Cookie 会话闭环） | Playwright 自带 Chromium v1243（本地缓存路径） | 单浏览器、本机确定性 Provider，与 CI 浏览器一致 |
| 136 tests | 2026-10-14 全量 pytest 记录 | 含 9 项会话管理与清理测试，合成数据 |
| 会话数量控制 | `tests/integration/test_auth_session_retention.py` | 本机批量清理，未验证生产会话规模 |
| 149 tests | 2026-10-14 全量 pytest 记录 | 含 13 项 OIDC 测试，合成账号与本地 IdP |
| OIDC 授权码 + PKCE | `tests/integration/test_oidc_login.py` | 假 IdP + 本地开发 IdP，**未与真实 IdP 联调** |
| 2 browser E2E | Playwright Chromium：企业登录闭环 + 工单闭环 | 单浏览器、本地 IdP、确定性 Provider |

## 演示顺序（5–7 分钟）

1. 用客户账号提交 429 问题，指出实时 Trace、引用 URI 和 Gate 后的回答。
2. 提交"无法解决，请创建工单"，强调只有草稿；点击确认后才发生低风险写入。
3. 切换支持账号，认领工单并推进状态，解释 Idempotency-Key 与 version 的区别。
4. 提交人工反馈，展示反馈只进入质量数据，不自动污染知识库。
5. 打开 80 场景报告，展示 401/403 如何在不降低阈值的前提下用受控多证据通过 Gate，并保留两条引用。

## 表述边界

- 不声称"服务真实企业客户""线上准确率 98.75%""生产节省多少人力"；
- 不把 Qwen macro-F1 写成 1.0——1.0 属于确定性 80 场景，Qwen 只有 7 条冒烟；
- 不声称"已经生产部署"——GitHub Actions 已验证镜像构建、整套 Compose 启动与短时探活，但未验证生产配置、容量、可用性或长期稳定性；
- 不声称已接入真实企业身份系统——只有本地开发用 IdP 与假 IdP 测试，未联调 Keycloak/Auth0/企业微信；
- 不声称会话管理达到生产设备管理能力——没有 IP、设备指纹、活跃会话数量上限与自动调度；
- 不声称 Cookie 会话已通过生产安全评审——没有设备列表、撤销全部会话、OIDC 和 HTTPS Cookie 的实测；
- 不声称已接入生产监控、告警或 SLO——Collector 当前只有 debug exporter，指标来自本机合成流量；
- 不声称"防住所有 Prompt Injection"——当前是规则预检、证据扫描和工具隔离的 MVP 防线。
