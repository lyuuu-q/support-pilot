# SupportPilot 最终证据快照

快照时间：2026-10-14（Asia/Shanghai）
数据性质：ExampleAPI 合成业务数据、人工标注合成评测集、合成账号；**不是生产数据**。
复现基线：上游 `EthanZ-zh/support-pilot` 的 `d4d65b4`。

## 复现与增量的边界

- 上游原有：ADR 0001–0007、阶段 2–8 的产品验收与学习文档、阶段 3/4 评测报告与检索 holdout 结果文件；
- 本仓库新增（2026-10-12 至 10-14）：阶段 9–20，对应 **ADR 0008–0019**，包含 claim 级忠实度、Agent 中止/重试、队列分页、checkpoint 与恢复、SSE 回放、前端断线恢复、历史保留与恢复锁、指标与维护、Cookie 会话与 CSRF、会话生命周期、OIDC 登录、指标后端与运维自动化；
- 复现记录：`docs/evaluation/reproduction-2026-10-12-fullstack.md`。

## 评测证据

| 层级 | 样本/检查 | 结果 | 解释边界 |
|---|---:|---:|---|
| RAG calibration | 50 正例 + 10 负例 | Recall@5 / MRR / nDCG@5 均 1.000 | 上游同源样本，仅用于校准与回归 |
| RAG deterministic holdout | 20 正例 + 10 负例 | Recall@5 1.000；MRR 1.000；nDCG@5 1.000；Gate P 1.000 / R 0.800 / F1 0.889（FP=0，FN=4） | 冻结后独立 ID 小样本 |
| RAG local BGE holdout | 20 正例 + 10 负例 | Recall@5 1.000；MRR 0.975；nDCG@5 0.982；Gate P 1.000 / R 0.950 / F1 0.974（FP=0，FN=1） | 本地 CPU，未进入常规覆盖率统计 |
| Agent deterministic（多证据版） | 80 场景 / 91 步 | 80/80；intent accuracy 与 macro-F1 1.000；工具参数/成功率 1.000；安全升级 Recall 1.000；高风险误执行 0；重复副作用 0；p50 56.15 ms / p95 66.94 ms | 确定性 Provider + `keyword-router-v1`，非对抗性红队 |
| Agent + checkpoint | 同上 | 80/80；p50 698.45 ms / p95 856.85 ms | 延迟换可恢复性，本机单机 |
| Faithfulness v2 | 12 条合成问题（8 条可回答） | support 1.000；citation precision 1.000；false answer 0.000；unsupported claim 0.000；claim coverage 0.8333 | 确定性 verifier，非生产忠实度 |
| Qwen 3.7 Plus 冒烟 | 7 条（5 次调用） | 7/7；¥0.0042 估算 | **历史记录，本轮未重跑**；只证明接入，不证明泛化 |
| 后端工程 | 154 tests | 全部通过 | 2026-10-14 本机实测 |
| 前端工程 | 16 tests + lint + build | 全部通过；JS gzip 66.0 kB | jsdom 单元/组件层 |
| 浏览器 E2E | 2 条（Playwright Chromium v1243） | 企业登录闭环、客户提问到人工处理闭环 | 单浏览器；确定性 Provider、隔离测试库 |
| 数据库迁移 | upgrade + check | head `0013`，无模型漂移 | 开发库与测试库均已应用 |
| 观测链路 | 指标导出端点 | 114 条 `support_pilot_*` 序列 / 13 指标族，导出记录 `results/metrics-snapshot-2026-10-14.json` | 合成流量、本机单实例；Prometheus 容器未在本机启动 |
| 会话与身份 | 26 项测试 | 会话基础 5、管理 5、清理 3、OIDC 13 | OIDC 只与本地开发用 IdP 联调 |
| 容器与 CI | Compose config + 历史 CI | 本机 `docker compose config` 通过；GitHub Actions 历史 4/4 成功 | 本机 Docker Hub 直连受限，镜像走加速站点；非生产部署 |

## 机器结果文件

- `results/agent-scenarios-v1-multi-evidence.json`（80/80，p50 56 ms）
- `results/agent-scenarios-v1-checkpoint.json`（80/80，p50 698 ms）
- `results/retrieval-holdout-deterministic-v1.json`、`results/retrieval-holdout-local-bge-v1.json`
- `results/faithfulness-deterministic-v1.json`
- `results/metrics-snapshot-2026-10-14.json`（本轮新增）

## 复现命令

```powershell
docker compose up -d postgres postgres-test
uv run alembic upgrade head
uv run python scripts/seed.py
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run ruff check .
uv run mypy
uv run pytest

Set-Location frontend
npm ci
npm run lint
npm run test
npm run build
$env:PLAYWRIGHT_BROWSERS_PATH = 'C:\Users\刘雨晴\Documents\github\.playwright-browsers'
npm run test:e2e

# 观测（可选）
docker compose --profile observability up -d otel-collector
uv run python scripts/metrics_snapshot.py --output docs/evaluation/results/metrics-snapshot-<日期>.json
```

## 环境限制（如实记录）

1. `cdn.playwright.dev` 对本机所在区域返回 403，Playwright 浏览器改用工作区已有缓存；CI 仍用自带 Chromium。
2. 本机镜像加速源无法拉取 Prometheus 镜像，Prometheus 服务与告警规则只做到配置正确并与埋点名称对齐，未做端到端抓取。
3. 未与真实 IdP（Keycloak/Auth0/企业微信）联调。
4. Qwen 冒烟为历史记录，本轮未重跑（未配置付费 Key）。
5. 计划任务脚本需要管理员权限，未实际注册。

## 表述边界

- 不声称生产部署、生产准确率、真实客户规模或节省人力；
- 确定性 Provider 的 1.000 不等于真实模型质量；Qwen 只有 7 条冒烟；
- 不声称防住所有 Prompt Injection；不声称具备生产监控、告警或 SLO 能力。
