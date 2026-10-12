# Claim 级引用与忠实度校验执行计划

**目标：** 在不生成新答案的前提下，为 RAG 与 Agent 增加 claim 级引用契约、确定性 verifier 和独立离线评测。
**设计：** `docs/superpowers/specs/2026-10-12-claim-level-citations-and-faithfulness-design.md`

## 步骤

### 1. 共享文本特征与契约

- [x] 记录设计边界和为什么先不改生成式答案；
- [x] 抽出共享 lexical feature 工具；
- [x] 增加 `EvidenceClaim`、`ClaimVerification` 契约；
- [x] 为 claim ID 和 citation index 建立稳定规则。

学习重点：为什么 claim 级引用不能只靠 chunk ID，契约要如何保持旧 API 兼容。

### 2. 确定性 verifier

- [x] 实现 claim 切分、归一化、技术标识精确检查与 token 覆盖率；
- [x] 增加正例、负例、技术标识缺失和中文 claim 测试；
- [x] 确保 verifier 不依赖任何外部模型。

学习重点：verbatim 与 lexical overlap 的边界，为什么不能把“由原文抽取”当作忠实度证明。

### 3. 检索与 Agent 集成

- [x] RAG 响应增加 `claims`，且只包含 supported claim；
- [x] Agent 回答复用同一 claim，保持现有 citations；
- [x] 集成测试覆盖单证据、多证据和不可答路径；
- [x] 确认 prompt injection 和安全升级路径不被绕过。

学习重点：RAG、LangGraph 和 API 契约之间的数据流。

### 4. 独立忠实度评测

- [x] 新增与 60/30 条检索集 ID 不重叠的 faithfulness v2 评测集；
- [x] 为可答问题标注 required claims、来源和必需术语；
- [x] 为不可答问题加入近邻难负例；
- [x] 实现 `scripts/evaluate_faithfulness.py`；
- [x] 输出 coverage、support rate、citation precision、false answer rate 和失败样本。

学习重点：coverage 与 faithfulness 的区别，为什么“引用多”不等于“回答忠实”。

### 5. 证据、文档与回归

- [x] 写入 ADR、评测报告和学习文档；
- [x] 更新 README 文档索引；
- [x] 运行 Ruff、Mypy、完整 pytest、评测脚本；
- [x] 如实记录失败样本和局限。

## 完成定义

- [x] 104 项既有测试不回归，并新增 claim/faithfulness 测试；
- [x] API 返回 claim 级引用且旧 citations 仍可用；
- [x] 评测报告包含样本量、Provider、时间、指标和失败项；
- [x] 不将合成结果表述为生产准确率。

