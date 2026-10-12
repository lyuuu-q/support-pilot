# 第九阶段：claim 级引用与忠实度验收

状态：已实现 deterministic Provider 的 claim 级引用、verifier 和独立离线评测
验证日期：2026-10-12

## 1. 交付范围

- [x] `EvidenceClaim` 与 `ClaimVerification` 契约；
- [x] 确定性 claim 抽取、原文包含校验、技术标识检查和加权词项覆盖；
- [x] RAG 与 Agent 响应返回 claim 级引用，原 chunk 级 citations 保持兼容；
- [x] 同一文档、主题和答案版本下的受控多证据扩展；
- [x] React 控制台展示 claim 文本、support 状态、citation index 和来源；
- [x] 12 条独立 faithfulness v2 评测集，8 个可答问题、4 个难负例；
- [x] coverage、support、citation precision、unsupported 和 false answer 指标；
- [x] ADR、评测报告和学习文档。

## 2. 验收证据

| 编号 | 行为 | 证据 |
|---|---|---|
| S9-AC-01 | claim 从原文抽取并能定位 chunk | `tests/unit/test_faithfulness.py` |
| S9-AC-02 | 技术标识不匹配时 verifier 拒绝 | `test_verifier_requires_exact_technical_identifier` |
| S9-AC-03 | RAG API 返回 claim 且 citation index 可定位 | `tests/integration/test_rag_api.py` |
| S9-AC-04 | Agent 回答返回同一批 claim | `tests/integration/test_agent_api.py` |
| S9-AC-05 | 多证据 claim 指向不同 citation | `test_agent_combines_same_topic_chunks_for_multi_evidence_answer` |
| S9-AC-06 | 独立评测集与 60/30 检索集不重叠 | `tests/unit/test_faithfulness_evaluation.py` |
| S9-AC-07 | 难负例 false answer rate 为 0 | 第九阶段评测报告 |
| S9-AC-08 | 无支持 claim 率为 0 | 第九阶段评测报告 |
| S9-AC-09 | React 控制台展示 claim 与来源 | `frontend/src/App.test.tsx` + Chromium E2E |

## 3. 结果

- 后端回归：113 passed，覆盖率 93%；
- 前端：4 项单元测试、lint、build 通过；Chromium E2E 1 passed；
- 80 场景 Agent 评测：80/80，重复副作用 0、高风险误执行 0；
- Claim support rate：1.000；
- Citation precision：1.000；
- Unsupported claim rate：0.000；
- False answer rate：0.000；
- Claim coverage：0.8333，仍有 3 个多事实问题未覆盖全部 required claims。

## 4. 边界

- 这是词法级忠实度校验，不是语义蕴含或人工逐主张审核；
- 评测集仍是合成知识，不是公开生产数据；
- 未覆盖 Qwen 生成答案、local BGE rerank、公开语料和逐主张人工复核；
- 覆盖率缺口必须保留说明，不能把 0.8333 表述为完整回答能力。
