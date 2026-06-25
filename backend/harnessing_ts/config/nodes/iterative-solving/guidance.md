本节点是可重复执行的迭代节点。
每次执行代表一轮完整迭代：先读取实时 runtime settings，提出 k 个候选解决方案，分配 subagent 分别做可行性测试和 case review，统一综合证据后选择本轮执行对象或下一轮方向，把需要保留的方法标准化为可复用工具，执行和分析结果，生成 candidate review、case review、iteration summary，决定是否结束或继续。

核心约束：
- 每轮必须在候选阶段提出 k 个候选解决方案。k 不是固定常量，必须在候选生成前调用 MCP `mcp__ts_harness__get_runtime_settings`，读取 `iterativeCandidateCount` 作为本轮 k；如果用户在前端实时修改 k，后续读取必须采用新值。
- 候选阶段不是方法排行榜或 baseline sweep。每个候选都必须围绕 contract、上一轮失败机制、reference knowledge graph 和数据证据形成清晰假设。
- 每个候选必须分配一个 subagent 使用 `Task` 独立测试和 review。subagent 的输出必须包括：候选假设、最小实现或复用工具路径、评估命令、指标、bad-case 抽样与 case review 结论、风险、是否建议进入统一方案。
- 主 node 负责统一综合所有 subagent 结果，记录为什么选择某个候选、组合候选、放弃候选或继续探索。不要让 subagent 直接调用 `mcp__ts_harness__finish_node`。
- 只有被统一综合后决定保留或执行的方案，才必须落盘为 `tools/` 下标准化工具或工具组合；被淘汰候选的代码可留在 `runs/iterations/<iteration-id>/candidates/<candidate-id>/`，但不得污染 `tools/registry.json`。
- 如果多个候选被组合，组合本身必须有明确接口、证据和风险说明，不能只是把多个结果并排报告。

必须完成：
- 读取 `user/problem-contract.md`，严格围绕 contract 的目标、输入输出、评价方式和停止条件工作。
- 读取 `user/data-spec.md`，所有工具构建、训练、推理、评估、case review 和输出预测文件都必须遵守其中定义的数据路径等要求。
- **必须调用 `mcp__ts_harness__query_knowledge`** 获取 reference knowledge graph 中的领域知识（如 ECG 异常类型定义、信号特征、常见方法、评价指标、bad case 归因线索等）。候选生成、case review 归因和 iteration summary 阶段都应按自然语言问题查询知识图谱。
- 普通知识检索不要直接读取 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**` 或 `knowledge_base/cache/**`。这些文件是 knowledge graph builder/reasoner 的内部存储；只有用户明确要求调试知识库文件、CSV schema 或图谱构建错误时才可以直接读取。
- 调用 `mcp__ts_harness__query_knowledge` 时默认不要请求原文证据详情。只有用户明确要求 citations/evidence，或本轮 case review 必须审计原始 reference 证据时，才设置 `includeEvidence=true`。
- 读取已有 `tools/**`、`reports/iterations/**` 和 `user/iteration-state.md`。首轮迭代时这些路径可以不存在；若不存在，应从 contract 和 data-spec 开始建立第一轮工具。
- 调用 `mcp__ts_harness__get_runtime_settings`，读取 `iterativeCandidateCount`，并在本轮候选审查报告中记录实际使用的 k。
- 根据 contract、上一轮 `user/iteration-state.md`、知识图谱查询结果和已有工具，提出 k 个候选对象：
  - 一种新工具方法，例如一个形态特征规则、一个相似度检索器、一个传统 ML 分类器、一个深度学习推理工具、一个 LLM 判断器、一个验证/审查工具。
  - 或一种已有工具组合，例如“先用形态特征筛查，再用上一轮相似度工具复核”。组合本身也必须是一个明确方案。
  - 或一种可能的优化策略，例如在原有方法上修改部分可变参数或新增特殊模块。优化策略本身也必须是一个明确方案。优化策略包括参数、阈值、窗口、特征开关或模块增量。
- 为每个候选创建 `runs/iterations/<iteration-id>/candidates/<candidate-id>/`，保存候选说明、subagent 测试记录、指标、样例输出、case review 摘要和风险。
- 调用 k 个 `Task` subagent。每个 subagent 只能审查自己负责的候选，不要互相覆盖文件；主 node 必须在收到全部结果后做统一综合。
- 运行训练、搜索、批量评估或其他可能卡住的命令时，必须为每个命令设置明确边界：优先使用 `timeout <duration> ...` 前台执行；若必须后台运行，必须把启动命令、当前 workspace 绝对路径、PID、stdout/stderr 和退出状态写入本候选或本轮 `runs/iterations/<iteration-id>/...` 下的记录文件。严禁用 `pkill`、`killall`、`pgrep` 管道、按脚本名/模型名模糊匹配或全局 `kill -9` 清理卡住任务。只能终止由当前 node/当前 subagent 在当前 workspace 启动且有记录可证明归属的 PID，并且先普通 `kill`、等待、复查；只有该 PID 仍存活且归属再次确认后才可对同一 PID 使用 `kill -9`。不得终止其他候选、其他 subagent、其他 workspace、Harness server、Claude/SDK runner 或用户进程；无法确认时不要 kill，把风险和残留 PID 写入候选报告。
- 写入 `reports/iterations/<iteration-id>-candidate-review.md`，至少包含候选列表、k 来源、每个候选的 subagent 输出摘要、指标对比、bad-case review 摘要、与 knowledge graph 的关联、淘汰/保留原因和统一结论。
- 将统一后本轮保留或执行的方法标准化落盘到 `tools/<tool-name>/` 或 `tools/generated/<tool-name>/`。至少包含：
  - 可调用入口，例如 Python module、CLI script 或函数封装。
  - 明确的输入输出接口，必须符合 `user/data-spec.md`。
  - `tools/<tool-name>/README.md`，说明工具用途、输入文件、输出文件、训练/拟合需求、调用命令、依赖、风险、适用条件和不适用条件。
  - 若本轮对象是已有工具组合，必须至少落盘一个 orchestration plan；如组合逻辑包含新判断/新流程，则需落盘为组合工具。
  - 若本轮对象是优化策略，则记录为 run config或新的tool version，不一定新建 tool 目录。
  - 若工具需要训练/拟合，训练状态、模型文件、参数和版本必须写入 `runs/iterations/<iteration-id>/` 或工具目录下的明确路径。
- 更新 `tools/registry.json` 和 `user/toolset-spec.md`，记录工具的 input、output、requires_training、use_when、risk、version、owner_iteration、artifact_paths。
- 形成当前轮解决方案，写入或更新 `user/solution-plan.md`。方案中必须引用本轮候选综合结论，并明确哪些候选被保留、组合或放弃。
- 执行方案，记录工具调用、训练/推理/验证命令、结果文件、指标和关键观察。所有本轮输出放入 `runs/iterations/<iteration-id>/`。
- 在写 summary 之前，必须先做整体结果分析和 case review。case review 的核心对象是 bad case；good case、边界样本和工具冲突样本只作为 bad case 归因的对照证据出现。
- 若 `tools/reference-feature-extractor/` 已通过后端校验，开始 case review 前必须读取 `manifest.json` 和 `README.md`，核对任务特定输入输出契约、`pythonApi`、源码入口和限制。后续应优先在实验或 case-review 脚本中按 README 以 Python module 方式 import 并调用该已验证 API；MCP `inspect_reference_feature_extractor` / `extract_reference_features` 可作为小输入 smoke test 或兼容入口，但不是大样本的强制路径。
- 对每个被分析的 bad case 以及用于对照的每个 good/prototype case，若 reference feature extractor 可用，必须实际调用已验证 extractor（Python API 或 MCP 均可），不得用肉眼或 LLM 自行判断替代。报告必须记录实际调用方式、工具路径、API 函数名、处理样本 ID、输出摘要和失败/警告；如果输出采用 `features` 结构，应记录 feature value、unit、judgment、rule 和 evidence。工具返回 `indeterminate` 或任务自定义不确定状态时必须如实保留。
- 每轮使用 reference feature extractor 时，应在 `runs/iterations/<iteration-id>/reference-feature-usage.json` 或等价 run artifact 中记录调用留痕：`toolPath`、`manifestPath`、`pythonApi`、调用模式（`python_module` 或 `mcp`）、样本数量、成功/失败数量、异常信息和输出文件路径。iteration 报告中声称使用 reference features 时必须能追溯到该调用记录。
- case review 必须产出完整报告 `reports/iterations/<iteration-id>-case-review.md`，至少包含：
  - **Case review scope**：定义本轮什么算作bad case。
  - **Sampling policy**：
    - 如果 bad case 总数少于或等于10 个，必须逐一分析每个 bad case。
    - 如果 bad case 很多，必须根据实际问题设计合理的采样策略，抽取至少 5 个、至多 20 个 bad case 进行深入分析。
    - 采样策略必须覆盖主要错误类型和风险来源，而不是只挑最容易解释的样本。
    - 报告中必须写清楚 bad case 总数、采样数量、采样维度、每个样本被选中的原因。
  - **Per-case visualization**：
    - 每个被分析样本都必须有样本可视化结果。若数据形态不支持，必须提供等价可解释视图并说明原因。时间序列任务应展示原始序列局部窗口、目标点/片段、预测结果、真实标签/参考答案、关键工具特征或 score；分类任务应展示原始样本或可解释视图、预测类别、真实类别和关键证据。
    - 所有可视化图片必须以 250 DPI 生成，保存到 `runs/iterations/<iteration-id>/case-review/visualizations/`，并在报告中使用正确的 Markdown 图片格式逐一引用，确保 case review 中能正确显示。
    - **Per-case analysis**：每个样本必须单独成节，包含：
    - 样本 ID、错误类型、真实结果、预测结果、score/confidence/rank 或其他当前方法输出。
    - 原始输入证据：从 `user/data-spec.md` 定义的原始字段读取并展示，不允许只看模型 score。
    - 当前方法证据：当前工具使用的特征、阈值、检索结果、模型中间输出、规则命中情况或训练/推理状态。
    - Reference feature evidence：若 reference feature extractor 可用，列出该 case 的完整工具调用结果；若不可用，明确标注 `reference feature extractor unavailable`，不得伪造对应判断。
    - 其他可能有用的信息：reference/domain knowledge、邻近样本、同类 prototype、nearest good case、历史轮次结果、工具冲突结果等。
    - 归因链路：按照“原始数据证据 → 当前方法行为 → 错误机制 → 领域/背景解释”的顺序分析为什么当前方法在该样本上失败。
    - 对照检查：至少和一个 good case、prototype 或 nearest reference case 等进行比较。如果提出某个特征是失败原因，必须检查该特征是否也大量出现在 good case 中。
    - 结论等级：标注 `explained`、`partially_explained` 或 `unexplained`。证据不足时必须写 `unexplained` 或 `partially_explained`，不要强行解释。
  - **Statistical analysis and synthesis**：
    - 在逐样本分析之后，必须对全部 bad case 或可计算的 bad case 集合做统计分析，而不是只总结抽样样本。
    - 至少统计 bad case 数量、错误类型分布、关键特征分布、score/confidence/rank 分布、与 good case 的差异、各分层指标、可解释/不可解释比例。
    - 最后总结当前方法的主要失败机制、证据强度、无法解释的范围、对下一轮工具或方案的具体影响。
  - **Summary insight visualization**：
    - 该步骤必须在所有选定 bad case 的逐样本分析和上述统计综合完成后执行。此时 agent 应先总结自己从样本证据中获得的“样本启发”，再思考哪种图形设计最能解释该启发；不要在逐 case 分析完成前预先绘制结论图，也不要生成与样本证据无关的装饰性图表。
    - agent 必须亲自完成可复现的可视化流程：确定要表达的启发与证据映射，设计图形结构，撰写绘图代码，按 `user/data-spec.md` 读取所需原始数据和方法输出，执行代码并检查生成结果。绘图代码、执行命令、输入路径和输出路径必须在本轮 run 工件或 case review 中可追溯。
    - summary 可视化可以是一张或多张，但每张都必须保存为 PNG，并写入 `runs/iterations/<iteration-id>/case-review/visualizations/`。文件名必须使用 `summary_` 前缀，后续语义名称使用下划线 `_` 分隔，例如 `summary_failure_patterns.png`；不得使用空格或连字符作为分隔符。
    - 每张 summary PNG 必须以 250 DPI 生成，画布宽高比必须为 16:9。强调色优先依次采用蓝、橙、绿、红；其他颜色只能作为中性背景、坐标、辅助线或确有必要的补充编码，并应保证图例和语义一致。
    - summary 可视化必须直接支撑 case review 中的样本启发、主要失败机制或下一轮方向。报告应逐图引用，并说明图片表达的启发、使用的数据范围、关键视觉编码以及不能从图中推出的结论。
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
  注意：这个文件是审计工件，不是主控制通道；但后端会用 `recommend_exit` 校验最后的 MCP `finish_node` 参数是否自洽。
- 最后输出一份本轮迭代总结报告 `reports/iterations/<iteration-id>-summary.md`，包含当前迭代的候选综合结论、最终保留或执行的方法/组合、工具落盘路径、执行结果、目标差距、case review 的高层结论和路径、下一轮迭代思路。summary 不能替代 case review。
- 本节点的硬契约产物包括 `tools/**`、`runs/iterations/<iteration-id>/**`、`reports/iterations/<iteration-id>-candidate-review.md`、`reports/iterations/<iteration-id>-case-review.md`、`reports/iterations/<iteration-id>-summary.md` 和 `user/iteration-state.md`。当新增可复用工具时，`tools/registry.json`、`user/toolset-spec.md`、`user/solution-plan.md` 需要生成且被 iteration summary 引用。

注意：
- 关注的是 agent 如何使用工具解决问题，不是研究方法排行榜。
- 不要把 k 个候选做成无边界的 sweep；每个候选必须有独立假设、独立 subagent review、明确证据和统一综合结论。
- 如果本轮不满足停止条件，最后调用 MCP `mcp__ts_harness__finish_node` 时必须设置 `loopDecision: "continue"` 且 `nextNode: "iterative-solving"`。
- 如果本轮满足停止条件，最后调用 MCP `mcp__ts_harness__finish_node` 时必须设置 `loopDecision: "exit"` 且 `nextNode: "final-summary"`。
- `user/iteration-state.md` 中的 `recommend_exit` 必须和 MCP 参数一致；后端会拒绝二者不一致的 `finish_node`。
- `goalMet` 表示 problem contract 目标或 contract 停止条件是否满足，不表示“本轮 node 是否完成”。如果继续下一轮，必须设置 `goalMet: false`。
- `finish_node.outputPaths` 必须包含本轮 candidate review、case review、summary 和 `user/iteration-state.md`。只有候选 subagent 报告、候选 metrics 或单个工具路径不足以完成本 node。
- 完成本节点只能调用 MCP `mcp__ts_harness__finish_node`。不要输出 `harnessControl` JSON，也不要期望后端从文件产物推断节点完成。
