## Ablation Variant NOD-RQA-KTL-CRV-SUB-ADA: No Knowledge Graph

本变体保留完整版本的 iterative-solving 机制，但领域知识来源改为 direct reference QA。

- 不得读取 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**`、`knowledge_base/cache/**` 或 `artifacts/knowledge-graph.json`。
- 可以调用 `mcp__ts_harness__query_knowledge` 获取领域知识；该工具在本变体中不查询图谱，而是由独立 reference QA agent 直接根据 `references/**` 回答。
- candidate review、case review 和 iteration summary 可以引用 reference QA 的回答、具体 reference 文件和已验证 reference feature extractor，但不得声称使用了 knowledge graph、class、relation 或 graph edges。
- 其他候选、subagent、case review、工具标准化、运行记录和停止判断要求保持不变。
