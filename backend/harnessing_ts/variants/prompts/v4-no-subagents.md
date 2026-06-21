## Ablation Variant V4: No Independent Subagents

保留与 V0 相同的 k 候选、候选定义、执行预算、指标和报告结构，但禁止创建 `Task` subagent；该工具不会提供。

- 当前 iterative-solving agent 必须按 candidate id 顺序逐个实现、运行测试和完成 review。
- 每个候选仍使用独立目录、相同输入 split、相同指标与预算上限，避免后执行候选获得额外资源。
- candidate review 中记录每个候选的顺序执行结果，但不得称其为 subagent 输出。
- 不得因为顺序执行而减少 k，或跳过某个候选的实现、测试、风险和 case review。

基础 guidance 中所有“必须调用 Task/独立 subagent”的条款由本 overlay 替换；其余 V0 契约不变。
