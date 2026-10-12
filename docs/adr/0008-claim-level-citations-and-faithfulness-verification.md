# ADR 0008：claim 级引用与确定性忠实度校验

- 状态：Accepted
- 日期：2026-10-12

## 背景

原有 RAG 与 Agent 返回 chunk 级 Citation，能够证明“答案使用了哪个文档片段”，但不能回答“答案中的哪条主张由哪条证据支持”。知识 chunk 常包含多个事实，多证据聚合后问题更明显；如果直接引入 LLM 生成答案，会进一步放大不可验证风险。

## 决策

1. 增加 `EvidenceClaim` 与 `ClaimVerification` 契约，claim 记录文本、chunk、source URI、citation index 和验证结果。
2. 从 Gate 通过并实际展示的 evidence 中抽取原子 claim；API 只返回 verifier 判定为 supported 的 claim。
3. verifier 使用确定性方法：先做归一化原文包含判断，再做技术标识精确检查和加权词项覆盖率判断；不调用模型。
4. 当同一文档、同一 topic_code、同一 answer_key 下有两个以上 chunk 各自通过 Answerability 阈值时，选择最高分组返回最多三个 chunk，以覆盖一个问题的多个事实；不降低 Provider 阈值。
5. 建立独立 faithfulness v2 评测集，标注 required claims、来源和必需术语，并加入共享业务词的难负例。
6. 评测报告 claim coverage、support rate、citation precision、unsupported claim rate 和 false answer rate。

## 备选方案

- 只做 LLM-as-judge：实现快，但缺少可重复基线，且与生成模型耦合。
- 一次性改成 LLM 生成答案：产品体验更强，但会同时改变生成、引用和评测三个变量，无法定位回归。
- 每个 chunk 永远全部返回：提高覆盖，但噪音大，且无法表示逐主张来源。

## 代价与限制

- 词法 verifier 不是语义蕴含，中文同义改写仍可能漏判；
- claim 抽取对文档分句质量敏感；
- 新评测集仍是合成知识，不能表述为生产公开数据；
- 剩余 required claim 缺失作为覆盖率失败如实保留，不通过降低阈值美化；
- 真正 LLM 生成答案时，需要人工复核或更强的 NLI/LLM judge 作为第二道评测。

## 验证方式

- claim 抽取、原文命中、技术标识缺失和无关主张单元测试；
- RAG/Agent API 的 claim 级引用集成测试；
- 独立 faithfulness v2 评测脚本与 JSON 结果；
- Ruff、Mypy 和完整 pytest 回归。
