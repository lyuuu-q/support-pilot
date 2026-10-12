# Claim 级引用与忠实度校验设计

## 目标

把当前“返回少量 chunk 级引用”的 RAG 输出提升为“每条可展示主张都能定位到具体引用”的结构，并建立不依赖 LLM 的忠实度校验和独立评测。

本增量不引入生成式答案，不改变 Answerability 阈值，不放宽安全要求。

## 问题

当前 `KnowledgeSearchResponse` 和 Agent 回答只有 chunk 级 `citations`，一条 chunk 可能包含多个事实。系统可以证明“引用了哪个 chunk”，但还不能机器证明“回答中的哪条主张由哪条证据支持”。

## 设计

1. 从被 Gate 通过并实际展示的 evidence chunk 中抽取原子 claim；
2. 每个 claim 记录来源 `chunk_id`、`source_uri`、`citation_index`；
3. 使用确定性 verifier 检查 claim 是否由引用内容支持；
4. API 只展示 verifier 判定为 supported 的 claim；
5. 独立评测集为可答问题标注 expected claims 与必需术语，为不可答问题保留难负例；
6. 评测跟踪 claim coverage、claim support rate、citation precision 和 false answer rate；
7. verifier 的负例单独做单元测试，避免“由原文抽取所以永远正确”的自我证明。

## 边界

- 只验证抽取式 claim；
- 中文语义等价仍受词法校验限制；
- 新评测集仍是项目合成知识，不表述为生产公开数据；
- 公开语料、逐主张人工复核和 LLM 生成答案忠实度留到后续增量。

## 验收

- chunk 级引用行为保持兼容；
- 每个展示 claim 都能定位到引用；
- 不支持的候选 claim 不会进入 Agent 回答；
- 独立评测脚本输出可复现 JSON；
- 单元、集成、Ruff、Mypy 和既有 104 项测试全部通过。
