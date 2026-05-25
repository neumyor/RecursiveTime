本节点是可重复执行的迭代节点。每次执行代表一轮完整迭代：选择一个本轮方法、把方法标准化为工具、执行方案、分析结果、case review、决定是否结束或继续。

核心约束：
- 每轮迭代只能尝试一种新方法，或者只尝试一种“此前已落盘工具的明确组合”。不要在同一轮中一次性尝试多种候选方法并选择最好的。
- 本节点不是方法排行榜，也不是 baseline sweep。每轮应该形成一个清晰假设：为什么这个单一方法或组合值得尝试，它针对上一轮或 contract 中的哪个问题。
- 任何提出的方法必须先落盘为 `tools/` 下的标准化工具，再被本轮方案调用。不要只在临时 notebook、一次性脚本或 Bash 片段中实现核心方法。

必须完成：
- 读取 `user/problem-contract.md`，严格围绕 contract 的目标、输入输出、评价方式和停止条件工作。
- 读取 `user/data-spec.md`，所有工具构建、训练、推理、评估、case review 和输出预测文件都必须遵守其中定义的数据路径、样本粒度、字段、标签、split、泄漏禁止项和预测格式。
- 读取已有 `tools/**`、`reports/iterations/**` 和 `user/iteration-state.md`。首轮迭代时这些路径可以不存在；若不存在，应从 contract 和 data-spec 开始建立第一轮工具。
- 根据 contract、上一轮 `user/iteration-state.md` 和已有工具，选择本轮唯一尝试对象：
  - 一种新工具方法，例如一个形态特征规则、一个相似度检索器、一个传统 ML 分类器、一个深度学习推理工具、一个 LLM 判断器、一个验证/审查工具。
  - 或一种已有工具组合，例如“先用形态特征筛查，再用上一轮相似度工具复核”。组合本身也必须是一个明确方案，而不是多方法并行评测。
- 将本轮方法标准化落盘到 `tools/<tool-name>/` 或 `tools/generated/<tool-name>/`。至少包含：
  - 可调用入口，例如 Python module、CLI script 或函数封装。
  - 明确的输入输出接口，必须符合 `user/data-spec.md`。
  - `tools/<tool-name>/README.md`，说明工具用途、输入文件、输出文件、训练/拟合需求、调用命令、依赖、风险、适用条件和不适用条件。
  - 若工具需要训练/拟合，训练状态、模型文件、参数和版本必须写入 `runs/iterations/<iteration-id>/` 或工具目录下的明确路径。
- 更新 `tools/registry.json` 和 `user/toolset-spec.md`，记录工具的 input、output、requires_training、use_when、risk、version、owner_iteration、artifact_paths。
- 形成当前轮解决方案，写入或更新 `user/solution-plan.md`。方案中只能引用本轮唯一方法/组合以及必要的数据读取、评估、可视化、case review 工具。
- 执行方案，记录工具调用、训练/推理/验证命令、结果文件、指标和关键观察。所有本轮输出放入 `runs/iterations/<iteration-id>/`。
- 做整体结果分析和 case review，至少覆盖成功样本、失败样本、边界样本、不确定样本和工具冲突样本。
- case review 必须产出完整报告 `reports/iterations/<iteration-id>-case-review.md`，至少包含：
  - case 选择标准和样本清单。
  - 每个 case 的输入证据、预测/判断结果、真实标签或参考答案、错误类型、可视化路径。
  - 每个 bad case 的数值证据表。必须从原始时间序列或工具特征中计算并保存可审计的数值归因证据。
  - bad case 与 good case / class prototype / nearest reference case 的对照。任何解释都必须给出 bad case 与对应 good case 的数值差异或相似度证据。
  - 当前迭代方法在哪些方面不足，例如特征不可观察、类别边界混淆、阈值脆弱、训练数据不足、泛化风险、工具接口不稳定、评估泄漏风险。
  - 可改进方向，明确下一轮可以尝试的优化方法或新方法。
    - 如果当前方法表现优异，只存在部分bad case且bad case具有一定的规律性和模式，建议对当前方法进行优化。具体来说，思考如何将相关规律性和模式固化为确定性的脚本代码，从而在当前方法的基础上进行优化。
    - 如果当前方法表现不好，或者存在大量无规律的bad case，则围绕问题和方法进行反思，思考是参数设置有误还是方法本身的固有缺陷。
- case review 的数值归因链路必须完整：
  - 先从 `user/data-spec.md` 找到原始输入字段，读取 bad case 的原始时间序列。
  - 观察per-case的时序变化特征，具体特征应结合任务和领域知识选择。
  - 基于数值证据解释错误原因，再关联参考资料中的领域知识。顺序必须是“数据证据 → 方法行为 → 领域解释”，不能反过来先套领域解释。
  - 检查归因是否与 good case 冲突：如果 bad case 的所谓异常/正常特征在大量 good case 中同样存在，就不能把它作为主要原因。
  - 如果数值证据不足以解释 bad case，必须明确写“当前证据无法解释”，并说明缺少什么信息或工具。
  - 对于可解释性低的特征（例如某些模型的输出）只能作为模型行为证据，不能单独作为 case 原因。
- 判断是否满足 contract 的结束条件。若满足，写明 recommend_exit=true；若不满足，写明下一轮迭代思路。
- 更新 `user/iteration-state.md`，记录当前轮次、是否建议退出、下一轮方向和关键阻塞。
- 输出一份本轮迭代总结报告 `reports/iterations/<iteration-id>-summary.md`，包含当前迭代的唯一方法/组合、工具落盘路径、执行结果、反思分析、case review 摘要和下一轮迭代思路。
- 本节点的硬契约产物只有 `tools/**`、`runs/iterations/<iteration-id>/**`、`reports/iterations/<iteration-id>-summary.md` 和 `user/iteration-state.md`。`tools/registry.json`、`user/toolset-spec.md`、`user/solution-plan.md`、`reports/iterations/<iteration-id>-case-review.md` 是推荐组织方式；若单独生成，必须被 iteration summary 引用。

注意：
- 关注的是 agent 如何使用工具解决问题，不是研究方法排行榜。
- 不要在一轮里写多个模型/方法然后比较选择。若需要探索多个方向，拆到多轮迭代。
- 如果本轮不满足停止条件，必须在 `user/iteration-state.md` 中写明 `recommend_exit: false`，后端会自动再次进入 iterative-solving。
- 如果本轮满足停止条件，必须在 `user/iteration-state.md` 中写明 `recommend_exit: true`，后端会进入 final-summary。
