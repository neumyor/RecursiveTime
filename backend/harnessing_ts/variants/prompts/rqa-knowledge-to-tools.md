## Ablation Variant NOD-RQA-KTL-CRV-SUB-ADA: No Knowledge Graph

本变体的 `knowledge-to-tools` 节点仍必须构建并通过后端校验 deterministic reference feature extractor，但不得依赖文件型知识图谱。

- 不得读取 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**`、`knowledge_base/cache/**` 或 `artifacts/knowledge-graph.json`。
- 需要领域定义、阈值、适用条件或 uncertainty 时，可以读取 `references/**`，也可以调用 `mcp__ts_harness__query_knowledge`；该工具在本变体中由独立 reference QA agent 直接根据 references 原文回答。
- `evidence-map.json`、`feature-plan.json`、`reference-rules.json` 和 `evaluation-report.json` 必须引用具体 reference 文件、章节、页码或文本片段；不得引用 graph class/relation 作为证据。
- 其他 extractor 文件、真实样本验证、control/reference evaluation 和 `validate_reference_feature_extractor` 要求保持完整版本不变。
