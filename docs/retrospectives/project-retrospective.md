# SupportPilot 项目复盘

## 做对了什么

- 先构建确定性业务基线再接模型，避免把权限、额度、状态迁移交给 LLM 猜；
- 每一阶段形成运行增量和机器结果，而不是一次生成大量空接口；
- 将 deterministic、本地 BGE、真实 Qwen 的评测口径严格分开；
- 通过幂等、version、唯一约束、行锁和审计把“创建工单”做成真实低风险写入；
- 保留失败样本：401/403 多证据覆盖不足时先升级人工，后续在不降低 Gate 的前提下增加受控同主题证据聚合。

## 实现中发现的问题

1. BGE CrossEncoder 已返回概率，重复 sigmoid 导致无答案样本全被放行；加入负例后才暴露并修复。
2. 中文单字稀释 HTTP 状态码等技术标识，确定性 Reranker 改为加权词项后修复 429 场景，并用原检索集回归。
3. TypeScript 7 与 typescript-eslint peer range 不兼容，依据实际安装错误降到 6.0 系列，而不是使用 `--force` 绕过。
4. SSE 网络 chunk 不等于事件边界，前端增加残片 buffer 和跨 chunk 测试。
5. Dockerfile/Compose 配置通过解析，本地 build 在 Docker Hub 鉴权地址超时；转到真实 GitHub runner 后完成镜像构建、Compose 启动和三条健康探测，同时仍未把短时 CI 探活扩大表述成生产部署。
6. 首次 GitHub Actions 运行让 Alembic 错连默认 `54329`，而 CI 数据库映射在 `54330`；补齐 `SUPPORT_PILOT_DATABASE_URL` 并增加工作流配置回归测试后修复。
7. 旧 JWT 篡改测试只替换 Base64URL 签名末字符；由于末字符可能包含未使用位，Linux 上偶然解码成原签名字节。改为替换签名首字符后，保证测试真正破坏签名并消除平台差异。
8. 原 60 条 RAG 数据同时用于校准和报告，满分无法说明泛化。拆分独立 ID 的 30 条 holdout，并在实现冻结后首次运行：本地 BGE Gate F1 为 0.974、FP=0、FN=1，如实保留这个安全升级，没有用测试失败反调阈值。

## 当前技术债

- 知识集小且为合成同业务域；虽已拆分 calibration/holdout，仍缺少真实公开数据和更大规模的分布外评测；
- 答案以抽取式为主，已支持同主题受控多证据聚合和 chunk 级引用，但尚未完成逐主张引用和忠实度评测；
- Agent 节点级 checkpoint 尚未持久化，只有会话与运行最终状态；
- JWT 无 refresh/MFA/revocation，浏览器使用 localStorage；
- 工单队列无游标分页、搜索和实时推送；Playwright 只覆盖 Chromium 主闭环，尚无断线恢复和多浏览器覆盖；
- OTel 未连接 Collector；Compose 仅完成 CI 短时启动与探活，尚无生产配置、容量和长期稳定性验证。

## 下一轮优先级

P0：在已拆分的 RAG calibration/test 上增加公开数据、难负例与逐主张引用/忠实度评测。
P1：补充 SSE Abort/恢复、队列分页、多浏览器覆盖和演示录像。
P2：OIDC/BFF 与 OTel Collector/指标/日志关联。
P3：只有在压测证明需要时，再拆检索或 Agent 服务。

## 复现与增量阶段复盘（2026-10-14）

### 相对上游技术债的闭合情况

| 上游技术债 | 本轮结果 |
|---|---|
| 缺少逐主张引用与忠实度评测 | 已实现 claim 级拆分 + 确定性 verifier，独立 faithfulness v2 数据集（support 1.000 / false answer 0.000 / coverage 0.8333） |
| Agent 只有最终状态、无节点级 checkpoint | 已用 PostgresSaver 持久化并支持中断恢复，代价是 p50 从 56 ms 升到 698 ms（如实记录） |
| JWT 无撤销、浏览器用 localStorage | 改为 HttpOnly Cookie 会话 + CSRF 双提交 + refresh 轮换 + 会话列表/撤销/清理 |
| 工单队列无分页与实时推送 | 游标分页 + SSE 事件持久化与回放 + 前端断线自动恢复 |
| Playwright 只覆盖 Chromium 主闭环 | 增加企业登录闭环；多浏览器明确定为不做（记录理由） |
| OTel 未接 Collector | Trace + Metrics + 指标导出端点 + 告警规则 + 维护/计划任务脚本 |

### 本轮做得好的地方

1. **先验证再声明**：每个阶段的数字都来自本机实测；无法验证的部分（Prometheus 容器、真实 IdP、Qwen 重跑、计划任务注册）逐条写进 ADR 与评测的"限制"里；
2. **分阶段小提交**：42 个提交每一条都能单独解释，便于回溯与审阅；
3. **不给指标起假名**：发现 Prometheus 单位后缀导致告警规则永远匹配不到数据后，先修名称，再加"告警指标必须真实存在"的测试；
4. **保守清洗判据**：会话清理只删已过期行，活跃会话在判定上不可能被选中。

### 本轮暴露的问题

1. 环境陷阱吃掉了不少时间：沙箱与文件属主不一致、`uv` 无法在沙箱内重建工程、CRLF/LF 导致文本替换静默失败、PowerShell 嵌套 here-string 解析问题；
2. 离线环境无法重跑 `uv lock`，`pyjwt[crypto]` 的锁文件元数据是手工按 uv 格式更新的（已用 `uv sync --frozen --offline` 验证可读）；
3. 两次写出过"假阳性"测试：CSRF 打到无需登录的接口、测试客户端 Cookie 域名写法导致 Cookie 根本没发出——都已修正，教训是身份/安全类断言必须先用反例证伪；
4. 启动浏览器需要额外授权，否则 Playwright 会静默挂起（不是失败，是卡住），排查成本高。

### 下一步

真实模型评测（30–50 条）、function calling 工具选择、公开演示环境、真实 IdP 与 Grafana/Tempo 看板。

