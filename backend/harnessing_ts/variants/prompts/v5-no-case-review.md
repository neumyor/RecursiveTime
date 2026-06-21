## Ablation Variant V5: No Case Review

本变体删除全部 case-level review：

- 不抽样 bad case，不做逐样本或 good-case 对照分析，不做错误机制统计归因。
- 不生成 case visualization、summary visualization 或 `reports/iterations/<id>-case-review.md`。
- subagent 只报告候选假设、实现、执行状态、聚合验证指标、成本和风险，不输出 case review。
- candidate selection、iteration summary 和停止判断只能依据聚合验证指标、执行状态、资源成本及 problem contract 中不依赖 case 分析的条件。
- `finish_node.outputPaths` 只需 candidate review、iteration summary 和 `user/iteration-state.md`，不包含 case-review。

基础 guidance 和 finish protocol 中所有 case-review、bad-case、逐样本、统计归因和可视化要求在本变体中禁用；其他 V0 流程保持不变。
