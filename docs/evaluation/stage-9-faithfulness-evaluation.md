# 第九阶段离线评测：claim 级引用与忠实度

- 运行时间：2026-10-12（Asia/Shanghai）
- 数据：`data/evaluation/faithfulness_v2_cases.json`
- 样本：12 条，8 个可答问题、4 个难负例
- Provider：deterministic / hash-lexical-v1 / weighted-token-overlap-v2
- 数据库：PostgreSQL 16 + pgvector 0.8.6
- 数据性质：人工设计合成问题，不是生产公开数据

## 指标

| 指标 | 结果 | 解释 |
|---|---:|---|
| Claim coverage | 0.8333 | required claims 中 3 个案例仍有缺口 |
| Claim support rate | 1.000 | 已验证候选中没有无支持 claim |
| Citation precision | 1.000 | 展示 claim 的 source_uri 均属于标注入源 |
| Unsupported claim rate | 0.000 | 候选 claim 没有被 verifier 误放行 |
| False answer rate | 0.000 | 4 个难负例均未被回答 |

首轮实现只返回单条最高分证据时 coverage 为 0.7708。加入“同一文档、同一 topic_code、同一 answer_key 且多个 chunk 各自过阈值”的受控多证据选择后提升到 0.8333，未降低 Answerability 阈值。

## 未通过覆盖的样本

| 案例 | Coverage | 缺失 required claim | 原因 |
|---|---:|---|---|
| faith-signature-body | 0.6667 | 签名输入是原始 HTTP request body 字节 | `签名输入` chunk 未达到单条证据阈值，当前只选中 `验证步骤` chunk |
| faith-pagination-cursor | 0.5000 | cursor 是不透明字符串 | `请求参数` chunk 未进入该分组的上方阈值证据 |
| faith-region-endpoint | 0.5000 | 新加坡区域使用 `ap-southeast-1` endpoint | `区域端点` chunk 未进入该分组的上方阈值证据 |

这些缺失被保留为失败项。没有通过降低 Provider 阈值或把全部 chunk 强制塞入答案来美化 coverage。

## 复现命令

```powershell
docker compose up -d postgres postgres-test
uv run alembic upgrade head
uv run python scripts/seed.py
uv run python scripts/ingest_knowledge.py --provider deterministic
uv run python scripts/evaluate_faithfulness.py
```

机器结果：`docs/evaluation/results/faithfulness-deterministic-v1.json`。

## 如何解读

- support rate 和 false answer rate 说明当前 claim 确实由引用原文支持，难负例没有被误答；
- coverage 仍受检索选片和词法 verifier 限制，不能表述为“所有问题都能完整覆盖”；
- 该评测证明 claim 级契约和 safety gate 可运行，不证明生产环境忠实度；
- 下一步需要公开语料、多相关 chunk 标注、中文同义改写和逐主张人工复核。
