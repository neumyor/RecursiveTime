# V7: No Knowledge-to-Tools Node

本变体跳过 `knowledge-to-tools` 节点。Node chain 退化为 `problem-contract → iterative-solving → final-summary`；主会话不在该节点构建确定性 reference feature extractor；`mcp__ts_harness__validate_reference_feature_extractor`、`extract_reference_features` 与 `inspect_reference_feature_extractor` 这三个工具都不会被注入。Case review 仍须使用原始数据和其他确定性数值工具完成归因，但不得声称使用了 reference feature extractor。
