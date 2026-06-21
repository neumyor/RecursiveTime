## Ablation Variant V2: Random Search

本变体禁止由 LLM 基于语义提出候选。仍须调用 `get_runtime_settings` 获取 k，并在相同的 k 候选执行预算下，从下列固定目录做随机采样：

- 预处理：`none`、`standard_scaler`、`robust_scaler`。
- 表征：`raw_flatten`、`summary_statistics`、`fft_statistics`、`lag_statistics`。
- 方法族：`logistic_regression`、`linear_svm`、`knn_euclidean`、`knn_dtw`、`random_forest`、`hist_gradient_boosting`。
- 参数空间：正则强度 `{0.01,0.1,1,10}`，kNN 邻居数 `{1,3,5,9,15}`，树数量 `{100,300,500}`，最大深度 `{none,4,8,16}`，学习率 `{0.03,0.1,0.3}`。只使用与抽中方法族相关的参数。

执行规则：

1. 每轮读取 k 后必须调用 V2 专用 MCP `mcp__ts_harness__sample_random_candidates`。后端会生成并记录 random seed，并从上述目录返回恰好 k 个不重复配置。不得自行生成 seed、重采样，或根据 contract、知识图谱、历史 bad case 或 LLM 偏好替换返回结果。
2. 如果某配置与数据形状技术上不兼容，将其记为执行失败并计入 k 预算；不得由 LLM 选择替代配置或额外重采样。
3. 每个抽中配置仍按 V0 相同的独立执行、指标、case review 和成本记录要求运行。
4. 只按 problem contract 预先定义的主验证指标选择最佳配置；并列时依次按辅助指标、较低成本、candidate id 决胜。
5. candidate review 必须记录完整目录、seed、采样顺序、配置、执行状态和选择规则，不能把随机结果重新解释为 LLM 提出的假设。

本 overlay 优先于基础 iterative-solving guidance 中“由 agent 提出候选”和“候选必须由领域假设产生”的要求；其他 V0 契约保持不变。
