## Ablation Variant NOD-RQA-SUB-ADA: No Knowledge Graph + No Case Review + No Knowledge Tools

本变体以 direct reference QA 为基础，同时跳过 `knowledge-to-tools` 节点并删除全部 case-level review：

- Node chain 退化为 `problem-contract → iterative-solving → final-summary`。
- 不构建 deterministic reference feature extractor；不要调用 validate/inspect/extract reference feature MCP 工具。
- 不抽样 bad case，不做逐样本或 good-case 对照分析，不做错误机制统计归因，不生成 case visualization 或 `reports/iterations/<id>-case-review.md`。
- `finish_node.outputPaths` 只需 candidate review、iteration summary 和 `user/iteration-state.md`，不包含 case-review。
- 可以调用 `mcp__ts_harness__query_knowledge` 获取 direct reference QA；不得读取或引用 knowledge graph 内部文件。

基础 guidance 中所有 knowledge-to-tools、reference feature extractor、case-review、bad-case、逐样本、统计归因和可视化要求在本变体中禁用；其他 direct reference QA 流程保持不变。
