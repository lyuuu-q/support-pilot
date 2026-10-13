# SupportPilot 复现与完善执行计划

**目标：** 先在当前 Windows 环境完整复现现有 deterministic 业务闭环与工程验证，再选择一个高价值方向形成带评测证据的后续增量。

**基线仓库：** `EthanZ-zh/support-pilot`
**基线提交：** `d4d65b4 feat: add minimal MCP knowledge search adapter (#5)`
**计划日期：** 2026-10-11
**数据边界：** ExampleAPI 业务数据与标注集均为合成数据；复现结果不得表述为生产准确率或生产部署证据。

## 1. 当前判断

这个项目适合作为首选，原因是它已经具备完整纵向链路，而不是聊天 Demo：

- 确定性业务基线：租户、权限、额度、事故、工单和审计；
- RAG：关键词/向量召回、RRF、Rerank、Answerability Gate 和 chunk 级引用；
- Agent：确定性 Provider、Qwen 意图适配、风险门控、多轮恢复和 SSE Trace；
- 安全闭环：JWT/RBAC、幂等写入、状态机、乐观锁、人工接管和 Prompt Injection 预检；
- 全栈：React 控制台、工单队列、反馈和人工处理；
- 工程交付：Alembic、pytest、Ruff、Mypy、Vitest、Playwright、OTel、Docker Compose 和 GitHub Actions。

需要注意：`docs/evaluation/final-evidence.md` 是 MCP 提交之前的历史快照。复现后必须重新运行并更新测试数量、CI 状态和证据时间，不能直接沿用旧数字。

## 2. 本机环境审计

已确认：

- Node.js `22.14.0`、npm `10.9.2` 已安装；
- Python 命令仅指向 `3.9.13`，低于项目要求的 Python 3.11+；
- 未发现 `uv`；
- 未发现 `docker`，也没有 Docker Desktop；
- `D:\model-cache` 尚不存在；
- C 盘剩余约 84 GiB，D 盘剩余约 35 GiB。

复现前需要：

- Python 3.12；
- uv 0.12.7（与 CI 一致）；
- Docker Desktop + WSL2；
- Node.js 24（与 CI 一致；当前 22.14 可先做前端冒烟，但最终验收使用 24）。

## 3. 执行原则

- 先复现，后修改；基线未全绿前不进入完善阶段；
- 先跑 deterministic Provider，不让 API Key、付费模型或外部通知影响基线；
- Qwen、SMTP、Webhook 和真实 OTel Collector 只做单独的可选验证；
- 每个阶段都记录提交号、命令、环境版本、结果和失败项；
- 每项改进必须先写清验收标准，再改实现；
- 不把合成小样本指标、CI 短时探活或单元测试表述为生产能力。

## 4. 阶段计划

### Phase 0：冻结基线与准备环境

状态：`[x]（2026-10-12 完成，见 docs/evaluation/reproduction-2026-10-12-fullstack.md）`

工作项：

- [ ] 安装 Python 3.12、uv 0.12.7 和 Docker Desktop；
- [ ] 确认 Docker 使用 WSL2，并验证 `docker compose version`；
- [ ] 从 `main` 创建本地工作分支，例如 `codex/reproduce-and-improve`；
- [ ] 确认工作区干净，记录 `git rev-parse HEAD`；
- [ ] 从 `.env.example` 生成本地 `.env`，生成至少 32 字符的 JWT Secret；
- [ ] 确认 `.env` 不在 Git 状态中；
- [ ] 将 Docker/Hugging Face/npm 缓存迁移或指向空间充足的磁盘；
- [ ] 记录 Python、uv、Node、npm、Docker 和系统版本。

验收：

- [ ] Python 3.12、uv 和 Docker 均可运行；
- [ ] Git 工作区无未计划改动；
- [ ] `.env`、Token、API Key 和本地缓存均未进入版本控制。

预计：0.5 天。

### Phase 1：复现后端 deterministic 基线

状态：`[x]（2026-10-12 完成，154 项后端测试中的基线部分）`

工作项：

- [ ] 启动 `postgres` 与 `postgres-test`；
- [ ] 执行 `uv sync --frozen --group dev`；
- [ ] 执行 Alembic upgrade 和 Alembic check；
- [ ] 播种合成数据；
- [ ] 使用 deterministic Embedding/Reranker 摄取知识；
- [ ] 运行 Ruff、Mypy 和完整 pytest/coverage；
- [ ] 启动 FastAPI，检查 ready 接口；
- [ ] 使用 `alpha.admin@example.com` 登录并完成 entitlement 查询；
- [ ] 验证高风险请求被拒绝且留下审计；
- [ ] 验证同一 Idempotency-Key 不重复创建工单；
- [ ] 记录本轮真实测试数量与覆盖率，不沿用 README 的历史数字。

验收：

- [ ] 迁移、种子和知识摄取成功；
- [ ] 静态检查、类型检查和后端测试通过；
- [ ] API 请求链路返回预期结果；
- [ ] 失败项与环境问题分开记录。

预计：1 天。

### Phase 2：复现前端、浏览器 E2E 与演示闭环

状态：`[x]（2026-10-12 完成；容器构建本机受 Docker Hub 阻断，由 CI 验证）`

工作项：

- [ ] 在 Node.js 24 环境下执行 `npm ci`；
- [ ] 执行 lint、Vitest 和 production build；
- [ ] 安装 Chromium 并运行 Playwright E2E；
- [ ] 运行 `scripts/demo.ps1`；
- [ ] 手工完成“知识回答 → 确认工单 → 支持人员认领 → 推进处理中”；
- [ ] 验证 SSE 引用、Trace、工单状态与审计记录；
- [ ] 执行 `docker compose config`；
- [ ] 在 Docker Hub 可访问时构建并启动 API/frontend；
- [ ] 记录容器验证是否真实完成，不用 GitHub Actions 历史结果代替本机结果。

验收：

- [ ] 前端 lint、单测和构建通过；
- [ ] Chromium 主闭环通过；
- [ ] 演示脚本通过且产出 ticket code、trace id；
- [ ] 若容器构建受网络阻断，明确标记为环境限制。

预计：1 天。

### Phase 3：形成可复现证据与代码认知

状态：`[ ]`

必须掌握的请求链路：

- [ ] 认证链路：登录、Argon2id、JWT、Bearer、租户授权、审计；
- [ ] Agent 链路：会话加载、安全预检、LangGraph、风险门控、工具调用、SSE、持久化；
- [ ] RAG 链路：metadata filter、双路召回、RRF、Rerank、Gate、组合证据、引用；
- [ ] 工单链路：草稿、显式确认、幂等键、事务、幂等重放和并发冲突；
- [ ] 人工链路：认领、版本检查、状态迁移、反馈和审计。

交付物：

- [ ] 新增复现记录，建议路径 `docs/evaluation/reproduction-2026-10-11.md`；
- [ ] 新增学习笔记，分别用“概述、请求链路、深入分析”三层解释核心实现；
- [ ] 更新架构图或补充一张本轮实际运行架构图；
- [ ] 准备 5 至 7 分钟演示脚本，覆盖 RAG、工单、人工接管和评测报告。

验收：

- [ ] 能脱离 README 白板讲清三条核心链路；
- [ ] 每个结论都能指向代码、测试、日志或报告；
- [ ] 明确区分 deterministic、local BGE、Qwen 和合成数据的结果边界。

预计：1 至 2 天。

## 5. 完善方向与排序

### P0：证据质量与答案忠实度 v2

状态：`[x]（阶段 9，ADR 0008）`

这是当前最高价值增量，因为它直接完善项目最强的 RAG/Agent 亮点。

计划：

- [ ] 定义独立于 calibration/holdout 的新评测集，加入公开来源、分布外问题和难负例；
- [ ] 记录来源、许可、版本、SHA-256 和标注方法；
- [ ] 扩展结果为 claim 级结构：claim、citation ids、支持状态和证据摘录；
- [ ] 增加确定性校验：引用存在、引文可追溯、数字/版本一致、冲突证据不被合并；
- [ ] 分别跟踪 Claim Support Precision/Recall、Citation Correctness、False Answer Rate；
- [ ] 冻结阈值后再运行测试集，保留失败样本；
- [ ] 将设计取舍写入新 ADR，并更新评测报告和关键指标口径。

验收：

- [ ] 新评测集与现有 60/30 条数据无 ID、模板和答案泄漏；
- [ ] 每条答案主张都能定位到证据；
- [ ] 不用降低 Answerability Gate 来美化指标；
- [ ] 新测试、Ruff、Mypy 和回归测试全部通过。

预计：2 至 3 天。

### P1：Agent checkpoint 与中断恢复

状态：`[x]（阶段 12，ADR 0011）`

计划：

- [ ] 评估使用 LangGraph Checkpointer 持久化节点状态；
- [ ] 明确与现有 `AgentConversation` 领域状态的职责边界；
- [ ] 支持中断、进程重启后恢复和重复确认；
- [ ] 增加崩溃窗口、并发确认和 SSE Abort/恢复测试；
- [ ] 记录 checkpoint 对状态一致性和运维复杂度的代价。

验收：

- [ ] 工单写入后、会话更新前模拟失败，重新请求不产生重复副作用；
- [ ] 可从可恢复节点继续，而不是从头重新执行；
- [ ] 不引入两套互相冲突的状态真相源。

预计：1 至 2 天。

### P2：控制台与工单队列可用性

状态：`[x]（阶段 11/13/14；多浏览器一项记录为不做）`

计划：

- [ ] 工单游标分页、搜索和状态筛选；
- [ ] SSE 断线重连、事件去重和取消；
- [x] ~~Playwright 覆盖 Chromium、Firefox、WebKit~~：**决定不做**（2026-10-14）。理由：本机浏览器 CDN 按地区封锁无法获取；Windows 上的 WebKit 并非 Safari，信号价值低；SSE/Cookie/OIDC 关键路径已由 Chromium 真实浏览器用例 + 后端测试覆盖。保留 Chromium 与系统浏览器通道。
- [ ] 增加反馈流转和人工接管的可视化回归；
- [ ] 如需实时队列，优先复用 SSE，不提前引入消息队列。

验收：

- [ ] 大数据量下队列加载不一次性全量拉取；
- [ ] 断线与重连不丢最终结果；
- [ ] 多浏览器 E2E 通过。

预计：1 至 2 天。

### P3：身份与可观测性生产化准备

状态：`[x]（阶段 16/17/18/19/20，ADR 0015–0019）`

计划：

- [ ] 将浏览器 Token 存储迁移到 BFF + HttpOnly/Secure Cookie，并处理 CSRF；
- [ ] 评估 refresh、撤销和 OIDC；
- [ ] 本地启动 OTel Collector，验证 API、SQL 和 Agent Span 关联；
- [ ] 增加检索延迟、Provider 调用、Token、成本和错误率指标；
- [ ] 仅在压测证明有必要时拆分检索或 Agent 服务。

验收：

- [ ] Token 不暴露给页面 JavaScript；
- [ ] 能从一次 Trace 关联 API、SQL 和 Agent 节点；
- [ ] 有可复现的指标看板或导出记录；
- [ ] 不把 Collector 演示写成生产稳定性验证。

预计：2 至 3 天。

## 6. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| Docker Desktop 安装或 WSL2 不可用 | 无法复现 PostgreSQL/pgvector 与 Compose | 先安装并重启；记录版本；必要时将容器验证标记为阻塞，不伪造结果 |
| Docker Hub 拉取超时 | 本机容器验收失败 | 先完成非容器测试；重试、配置镜像源或使用 CI，明确区分 |
| Hugging Face 模型下载失败 | local BGE 评测无法运行 | deterministic 基线照常完成；模型缓存不进入 Git |
| Qwen API Key 或费用未准备 | 真实 Provider 冒烟无法复跑 | 将 Qwen 标记为可选验证，不与 deterministic 验收混用 |
| README 证据快照过期 | 对外指标不准确 | 以最新提交和本轮机器结果重建 `final-evidence` |
| 改进范围过大 | 基线稳定后仍无法形成闭环 | 每轮只做 P0 或一个 P1，并设置明确完成定义 |
| 新评测集与旧数据同源 | 指标虚高 | 独立 ID、来源和模板审计；冻结阈值后只跑一次 |

## 7. 交付与完成定义

最终完成时应有：

- [ ] 一条从干净环境开始、可复制执行的复现记录；
- [ ] 后端、前端、E2E、迁移和容器验证的新鲜结果；
- [ ] 至少一个完成设计、实现、测试和评测的 P0 增量；
- [ ] ADR、产品/验收文档、评测报告和 README 同步；
- [ ] 5 至 7 分钟可重复演示；
- [ ] 未解决风险和失败样本如实披露；
- [ ] 工作区无密钥、缓存、构建产物和无关改动。

## 8. 推荐执行入口

下一步直接执行 Phase 0，然后连续推进到 Phase 1。只有当后端 deterministic 基线、前端主闭环和 E2E 全绿后，才开始 P0“证据质量与答案忠实度 v2”。

## 9. 收尾说明（2026-10-14）

状态：本计划的阶段与 P0–P3 全部收口；不可验证项已显式记录为不做或限制，见下。

### 已完成

- 复现：环境、后端 deterministic 基线、前端、浏览器 E2E、Compose 校验，均有本轮实测记录；
- P0 证据质量：claim 级引用、忠实度 v2 独立数据集与确定性 verifier；
- P1 可恢复性：LangGraph checkpoint、恢复并发锁、历史保留清理；
- P2 可用性：工单队列游标分页、SSE 事件持久化与回放、前端断线自动恢复；
- P3 生产化准备：OTLP Trace + Metrics、指标导出端点与告警规则、Cookie 会话 + CSRF、会话生命周期与清理、OIDC 登录、维护与计划任务脚本。

### 明确不做（记录理由，而非欠账）

- **Firefox/WebKit 多浏览器 E2E**：本机浏览器 CDN 区域封锁；Windows 上的 WebKit 并非 Safari；关键路径已由 Chromium 真实用例与后端测试覆盖；
- **真实 IdP 联调**：需要外部账号与网络，本阶段只交付并验证客户端侧（含本地开发用 IdP）；
- **Grafana 看板 / Alertmanager 通知 / 长期存储**：本机无法拉取 Prometheus 镜像，交付的是导出端点 + 抓取与告警配置 + 指标快照；
- **拆分检索/Agent 服务**：计划中本就写明"仅在压测证明有必要时"再做，本轮未做压测。

### 后续建议（超出本计划）

1. 用真实模型（Qwen）在 30–50 条意图/回答/门控用例上重跑评测，并做 prompt 版本对比；
2. 增加 function calling 形式的工具选择与失败重试，并扩评测集；
3. 部署一个公开可访问的演示环境，附架构图与录屏；
4. 接入真实 IdP 与 Grafana/Tempo，补成本与延迟看板。
