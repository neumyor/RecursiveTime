## Ablation Variant NOD-RQA-CRV-SUB-ADA: No Knowledge Graph + No Knowledge Tools

本变体以 direct reference QA 为基础，但跳过 `knowledge-to-tools` 节点，不构建 deterministic reference feature extractor。

- Node chain 退化为 `problem-contract → iterative-solving → final-summary`。
- `mcp__ts_harness__validate_reference_feature_extractor`、`extract_reference_features` 与 `inspect_reference_feature_extractor` 不会被注入；不要尝试调用。
- case review 仍须使用原始数据和其他确定性数值工具完成归因，但不得声称使用了 reference feature extractor。
- 可以调用 `mcp__ts_harness__query_knowledge` 获取 direct reference QA；不得读取或引用 knowledge graph 内部文件。
