# 第九阶段学习说明：claim 级引用与忠实度校验

## 1. 这次要解决什么

原来系统可以说“答案引用了哪几个 chunk”，但不能机器回答“答案中的哪条主张由哪条证据支持”。本阶段把证据最小单位从 chunk 降到 claim，并增加不依赖模型的 verifier 和独立评测。

## 2. 阅读顺序

1. `docs/superpowers/specs/2026-10-12-claim-level-citations-and-faithfulness-design.md`：目标和边界；
2. `src/support_pilot/rag/text.py`：共享词项特征；
3. `src/support_pilot/rag/faithfulness.py`：claim 抽取和验证；
4. `src/support_pilot/rag/retrieval.py`：claim 如何进入 RAG 响应；
5. `src/support_pilot/agent/workflow.py`：Agent 如何复用 claim；
6. `scripts/evaluate_faithfulness.py`：独立评测；
7. `frontend/src/App.tsx` 与 `frontend/src/types.ts`：claim 如何展示；
8. `docs/evaluation/stage-9-faithfulness-evaluation.md`：结果和失败。

## 3. 每一步为什么这样做

### Step 1：先定义 claim 契约

原因：如果直接把 chunk 拆成句子，只是改变字符串格式，调用方无法知道每条主张引用哪条证据。增加 `EvidenceClaim` 和 `ClaimVerification` 后，`claim -> chunk_id -> source_uri -> citation_index` 形成可检查链路。

关键设计：`claims` 是增量字段，旧的 chunk 级 `citations` 和现有调用方保持兼容。

### Step 2：为什么用确定性 verifier

原因：忠实度如果由同一个 LLM 判断，会形成自证循环；CI 也需要不花模型费用的可重复结果。

实现分两层：

- 原文包含：claim 归一化后直接出现在 cited content 中，方法标记 `verbatim`；
- 加权词项覆盖：技术标识必须精确命中，中文按字符和 bigram 加权。

限制：词法覆盖不是语义蕴含；同义改写可能漏判，不能写成“已经解决所有幻觉”。

### Step 3：为什么不能只在评测脚本里生成 claim

原因：只有产品请求链路返回 claim，用户、Agent、前端和评测才能共享同一份证据结构。

Agent 仍然遵守原顺序：Answerability Gate → Prompt Injection 检查 → citations/claims → 回答。这个顺序保证不可信证据不会先进入答案。

### Step 3.5：为什么增加受控多证据

第一轮评测 coverage 只有 0.7708。失败原因不是 claim 抽取，而是一个用户问题包含两个事实，但两个事实在同文档的不同 chunk，最高分 chunk 只覆盖其中一个。

改进：同一文档、同一 `topic_code`、同一 `answer_key` 下，如果有两个以上 chunk 各自通过 Answerability 阈值，就选最高分组最多三个 chunk。没有降低 Provider 阈值；不足阈值时仍走原有安全升级。

结果 coverage 提升到 0.8333，false answer rate 仍为 0。

### Step 4：为什么 required claim 覆盖率比“引用数”更重要

只统计引用数量会奖励“多贴文档”，但不证明回答覆盖用户问题。required claims 把用户问题拆成必须出现的事实：

- coverage 检查“该说的有没有说”；
- support rate 检查“说了的是否由证据支持”；
- citation precision 检查“引用来源是否相关”；
- false answer rate 检查“无答案问题有没有硬答”。

### Step 5：为什么保留 3 个覆盖失败

剩余失败是 `签名输入`、`cursor 不透明`、`新加坡 endpoint` 三个 chunk 没达到单条阈值。可以把阈值降下来，但那样会让安全门控变松，换来的只是更好看的小样本分数。保留失败比调参更重要。

### Step 6：为什么还要做前端展示

原因：API 返回 claim 不等于用户能看见 claim。如果 React 仍只展示 chunk 级引用，用户无法判断回答中的每句话来自哪里。

实现：结果面板增加“逐条主张”，每条显示 claim ID、claim 文本、support 状态、citation index 和 source_uri；原“引用证据”保留，形成 claim 到 chunk 的两级证据视图。

验证：Vitest 断言 claim 文本和“支持”状态；Chromium E2E 断言“逐条主张”列表包含 `Retry-After`。
## 4. 验收结果

- 后端完整测试：113 passed，覆盖率 93%；
- 既有检索 holdout：Recall@5 1.000、MRR 1.000、nDCG@5 1.000、Gate F1 0.889，不回归；
- 80 场景 Agent 评测：80/80，重复副作用 0、高风险误执行 0；
- 前端：4 项单元测试、lint、build 通过；Chromium E2E 1 passed，并断言 claim 级“逐条主张”展示；
- claim support rate：1.000；
- citation precision：1.000；
- unsupported claim rate：0.000；
- false answer rate：0.000；
- claim coverage：0.8333，3 个失败项如实保留。

## 5. 面试时怎么讲

“我把 RAG 的证据粒度从 chunk 降到 claim，用确定性 verifier 检查每条 claim 是否由引用原文支持；同时保留独立难负例评测，区分覆盖率和忠实度。第一轮 coverage 0.7708，分析发现是同一文档跨 chunk 的多事实问题，于是增加不降低阈值的受控多证据，提升到 0.8333，同时 false answer 和 unsupported 都保持 0。剩余缺口没有通过调阈值美化。”
