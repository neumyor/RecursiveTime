## Ablation Variant V3: No Knowledge Graph

本变体不得调用 `query_knowledge`，也不得读取 `references/**`、`knowledge_base/**` 或 reference knowledge 工件。候选生成、错误归因和下一轮方向只能使用：

- `user/problem-contract.md` 与 `user/data-spec.md`；
- 当前和历史 run 的聚合指标、执行状态与成本；
- 原始数据和可审计的数据证据；
- 已有工具及历史 iteration 工件。

candidate review、case review 和 summary 中不得声称使用了领域图谱或 reference 证据。基础 guidance 中所有强制知识查询条款在本变体中禁用，其他流程保持 V0 不变。
