## Ablation Variant V6: One-Shot Harness

本变体只允许一次 iterative-solving：

- 本轮仍完整执行 k 候选、独立 Task subagent、candidate review、工具标准化、case review、统计综合和可视化。
- k 由 `get_runtime_settings` 返回；如实验设计需要把 V0 平均候选总预算集中到本轮，应在启动前或本轮开始前设置对应的 `iterativeCandidateCount`，并在报告中记录。
- 无论是否达到指标目标，本轮结束都必须写 `recommend_exit: true`，说明 one-shot ablation budget exhausted。
- `finish_node` 必须使用 `loopDecision: "exit"` 和 `nextNode: "final-summary"`；后端会拒绝 `continue` 或第二次进入 iterative-solving。
- 最终总结必须区分“达到 contract 目标”和“因 one-shot 预算强制停止”。

除禁止后续迭代外，其余 V0 契约不变。
