## Ablation Variant NOD-RQA-KTL-CRV-SUB-ADA: No Knowledge Graph

本变体保留完整 node chain、references、candidate/subagent、case review、`knowledge-to-tools` 和 adaptive stop，但禁用文件型知识图谱构建与图谱检索。

- 不得要求或等待 Knowledge Graph builder；不得读取 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**`、`knowledge_base/cache/**` 或 `artifacts/knowledge-graph.json`。
- 可以读取 `references/**`，也可以在系统注入时调用 `mcp__ts_harness__query_knowledge`；该工具在本变体中由独立 reference QA agent 直接读取所有 references 回答，不依赖图谱。
- problem contract 和 data spec 应基于用户需求、references 原文、直接 reference QA、原始数据 exploration、可观察字段和评价约束建立。
- 不生成 `knowledge_base/domain-brief.md` 作为图谱构建输入；若需要领域摘要，应写在 problem contract 中并标注来自 reference QA 或具体 reference 文件。
