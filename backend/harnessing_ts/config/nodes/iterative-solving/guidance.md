本节点是可重复执行的迭代节点。
每次执行代表一轮完整迭代：选择一个本轮方法、把方法标准化为可复用的工具、执行方法、分析结果、生成 case review、生成 iteration summary、决定是否结束或继续。

核心约束：
- 每轮只能尝试一个唯一对象：一种新方法、一种已有工具组合，或一种明确优化策略。不要在同一轮中一次性尝试多种候选方法并选择最好的。
- 本节点不是方法排行榜，也不是 baseline sweep。每轮应该形成一个清晰假设：为什么这个单一方法或组合值得尝试，它针对上一轮或 contract 中的哪个问题。
- 对于提出的方法和策略，先落盘为 `tools/` 下的标准化工具，再被本轮方案调用。不要只在临时 notebook、一次性脚本或 Bash 片段中实现核心方法。

必须完成：
- 读取 `user/problem-contract.md`，严格围绕 contract 的目标、输入输出、评价方式和停止条件工作。
- 读取 `user/data-spec.md`，所有工具构建、训练、推理、评估、case review 和输出预测文件都必须遵守其中定义的数据路径等要求。
- 读取已有 `tools/**`、`reports/iterations/**` 和 `user/iteration-state.md`。首轮迭代时这些路径可以不存在；若不存在，应从 contract 和 data-spec 开始建立第一轮工具。
- 根据 contract、上一轮 `user/iteration-state.md` 和已有工具，选择本轮唯一尝试对象：
  - 一种新工具方法，例如一个形态特征规则、一个相似度检索器、一个传统 ML 分类器、一个深度学习推理工具、一个 LLM 判断器、一个验证/审查工具。
  - 或一种已有工具组合，例如“先用形态特征筛查，再用上一轮相似度工具复核”。组合本身也必须是一个明确方案，而不是多方法并行评测。
  - 或一种可能的优化策略，例如在原有方法上修改部分可变参数或新增特殊模块。优化策略本身也必须是一个明确方案。优化策略包括参数、阈值、窗口、特征开关或模块增量。
- 将本轮方法标准化落盘到 `tools/<tool-name>/` 或 `tools/generated/<tool-name>/`。至少包含：
  - 可调用入口，例如 Python module、CLI script 或函数封装。
  - 明确的输入输出接口，必须符合 `user/data-spec.md`。
  - `tools/<tool-name>/README.md`，说明工具用途、输入文件、输出文件、训练/拟合需求、调用命令、依赖、风险、适用条件和不适用条件。
  - 若本轮对象是已有工具组合，必须至少落盘一个 orchestration plan；如组合逻辑包含新判断/新流程，则需落盘为组合工具。
  - 若本轮对象是优化策略，则记录为 run config或新的tool version，不一定新建 tool 目录。
  - 若工具需要训练/拟合，训练状态、模型文件、参数和版本必须写入 `runs/iterations/<iteration-id>/` 或工具目录下的明确路径。
- 更新 `tools/registry.json` 和 `user/toolset-spec.md`，记录工具的 input、output、requires_training、use_when、risk、version、owner_iteration、artifact_paths。
- 形成当前轮解决方案，写入或更新 `user/solution-plan.md`。方案中只能引用本轮唯一方法/组合以及必要的数据读取、评估、可视化、case review 工具。
- 执行方案，记录工具调用、训练/推理/验证命令、结果文件、指标和关键观察。所有本轮输出放入 `runs/iterations/<iteration-id>/`。
- 在写 summary 之前，必须先做整体结果分析和 case review。case review 的核心对象是 bad case；good case、边界样本和工具冲突样本只作为 bad case 归因的对照证据出现。
- case review 必须产出完整报告 `reports/iterations/<iteration-id>-case-review.md`，至少包含：
  - **Case review scope**：定义本轮什么算作bad case。
  - **Sampling policy**：
    - 如果 bad case 总数少于或等于10 个，必须逐一分析每个 bad case。
    - 如果 bad case 很多，必须根据实际问题设计合理的采样策略，抽取至少 5 个、至多 20 个 bad case 进行深入分析。
    - 采样策略必须覆盖主要错误类型和风险来源，而不是只挑最容易解释的样本。
    - 报告中必须写清楚 bad case 总数、采样数量、采样维度、每个样本被选中的原因。
  - **Per-case visualization**：
    - 每个被分析样本都必须有样本可视化结果。若数据形态不支持，必须提供等价可解释视图并说明原因。时间序列任务应展示原始序列局部窗口、目标点/片段、预测结果、真实标签/参考答案、关键工具特征或 score；分类任务应展示原始样本或可解释视图、预测类别、真实类别和关键证据。
    - 可视化文件应保存到 `runs/iterations/<iteration-id>/case-review/` 或同等明确路径，并在报告中使用正确的markdown格式逐一引用，确保case review中能正确显示。
  - **Per-case analysis**：每个样本必须单独成节，包含：
    - 样本 ID、错误类型、真实结果、预测结果、score/confidence/rank 或其他当前方法输出。
    - 原始输入证据：从 `user/data-spec.md` 定义的原始字段读取并展示，不允许只看模型 score。
    - 当前方法证据：当前工具使用的特征、阈值、检索结果、模型中间输出、规则命中情况或训练/推理状态。
    - 其他可能有用的信息：reference/domain knowledge、邻近样本、同类 prototype、nearest good case、历史轮次结果、工具冲突结果等。
    - 归因链路：按照“原始数据证据 → 当前方法行为 → 错误机制 → 领域/背景解释”的顺序分析为什么当前方法在该样本上失败。
    - 对照检查：至少和一个 good case、prototype 或 nearest reference case 等进行比较。如果提出某个特征是失败原因，必须检查该特征是否也大量出现在 good case 中。
    - 结论等级：标注 `explained`、`partially_explained` 或 `unexplained`。证据不足时必须写 `unexplained` 或 `partially_explained`，不要强行解释。
  - **Statistical analysis and synthesis**：
    - 在逐样本分析之后，必须对全部 bad case 或可计算的 bad case 集合做统计分析，而不是只总结抽样样本。
    - 至少统计 bad case 数量、错误类型分布、关键特征分布、score/confidence/rank 分布、与 good case 的差异、各分层指标、可解释/不可解释比例。
    - 最后总结当前方法的主要失败机制、证据强度、无法解释的范围、对下一轮工具或方案的具体影响。
- case review 的数值归因链路必须完整：
  - 先从 `user/data-spec.md` 找到原始输入字段，读取 bad case 的原始时间序列。
  - 观察per-case的时序变化特征，具体特征应结合任务和领域知识选择。
  - 基于数值证据解释错误原因，再关联参考资料中的领域知识。顺序必须是“数据证据 → 方法行为 → 领域解释”，不能反过来先套领域解释。
  - 检查归因是否与 good case 冲突：如果 bad case 的所谓异常/正常特征在大量 good case 中同样存在，就不能把它作为主要原因。
  - 如果数值证据不足以解释 bad case，必须明确写“当前证据无法解释”，并说明缺少什么信息或工具。
  - 对于可解释性低的特征（例如某些模型的输出）只能作为模型行为证据，不能单独作为 case 原因。
- case review 与 summary 必须充分区分：
  - `reports/iterations/<iteration-id>-case-review.md` 只回答“哪些 bad case 被选中、每个 bad case 原始数据是什么样、可视化在哪里、当前方法为什么在该样本上出错、这些错误在统计上有什么共性、哪些无法解释”。它应以采样策略、逐样本可视化、逐样本归因、对照样本、统计分析和失败机制为主。
  - `reports/iterations/<iteration-id>-summary.md` 只回答“本轮构建或选择了什么工具/方法，如何调用，整体指标和目标差距如何，case review 的统计性结论是什么，下一轮或退出决策是什么”。它不应包含逐个 bad case 的详细分析、原始窗口、长表格或可视化解读；这些只能留在 case review 中。summary 只能引用 case review 路径和 3-5 条高层结论。
  - 生成顺序必须是：先写并检查 case review，再基于 case review 写 summary。summary 中必须显式引用本轮 case review 路径。
- 判断是否满足 contract 的结束条件。这个判断必须同时体现在审计工件和 MCP 结构化控制参数中。
- 更新 `user/iteration-state.md`，记录当前轮次、是否建议退出、下一轮方向和关键阻塞。文件开头保留机器可读审计块，且字段名不要加 Markdown 粗体、标题符号或中文标点：
  ```yaml
  recommend_exit: false
  current_iteration: "001"
  next_iteration: "002"
  exit_reason: ""
  ```
  如果满足退出条件，则写 `recommend_exit: true`，并在 `exit_reason` 中说明依据。
  注意：这个文件只是审计工件，不能作为节点流转控制通道。真正的流转决策必须通过最后的 MCP `finish_node` 参数传给后端。
- 最后输出一份本轮迭代总结报告 `reports/iterations/<iteration-id>-summary.md`，包含当前迭代的唯一方法/组合、工具落盘路径、执行结果、目标差距、case review 的高层结论和路径、下一轮迭代思路。summary 不能替代 case review。
- 本节点的硬契约产物包括 `tools/**`、`runs/iterations/<iteration-id>/**`、`reports/iterations/<iteration-id>-case-review.md`、`reports/iterations/<iteration-id>-summary.md` 和 `user/iteration-state.md`。当新增可复用工具时，`tools/registry.json`、`user/toolset-spec.md`、`user/solution-plan.md` 需要生成且被 iteration summary 引用。

注意：
- 关注的是 agent 如何使用工具解决问题，不是研究方法排行榜。
- 不要在一轮里写多个模型/方法然后比较选择。若需要探索多个方向，拆到多轮迭代。
- 如果本轮不满足停止条件，最后调用 MCP `mcp__ts_harness__finish_node` 时必须设置 `loopDecision: "continue"` 且 `nextNode: "iterative-solving"`。
- 如果本轮满足停止条件，最后调用 MCP `mcp__ts_harness__finish_node` 时必须设置 `loopDecision: "exit"` 且 `nextNode: "final-summary"`。
- `user/iteration-state.md` 中的 `recommend_exit` 必须和 MCP 参数一致，但后端不会解析该文件来控制流转。
- 完成本节点只能调用 MCP `mcp__ts_harness__finish_node`。不要输出 `harnessControl` JSON，也不要期望后端从文件产物推断节点完成。
