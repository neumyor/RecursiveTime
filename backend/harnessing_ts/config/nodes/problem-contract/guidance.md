本节点负责把“用户想做什么”落成可执行 contract，而不是直接进入工具迭代。

本阶段的用户侧 output 必须包括两个锚点工件：
- `user/problem-contract.md`：定义任务目标、评价方式、迭代终止条件和后续 required artifacts。
- `user/data-spec.md`：定义后续所有工具、训练、推理、评估和 case review 必须遵守的数据规范。

必须完成：
- 用户输入主要用于明确任务目标、数据来源要求、输出期望和约束条件。不要把用户输入当作领域知识来源；领域知识主要来自 references/**。
- references/** 可能包含学术论文、指南、说明文档或用户整理材料，格式可能是 PDF、DOCX、TXT、MD 或其他文本文件。必须构建或调用规范读取工具来读取这些资料：
  - PDF：直接使用 Claude Code SDK 原生 `Read` 工具读取；不要优先构建额外 PDF 抽取/OCR 工具，除非 `Read` 明确无法读取或内容明显缺失。
  - DOCX：优先读取系统生成的同名 `.docx.txt`；若不存在，使用 `uv run python tools/read_docx.py <docx> <output.txt>` 抽取。
  - TXT/MD：可直接读取，但需要将关键领域知识整理到结构化摘要中。
  - 对每个 reference 记录读取方式、抽取产物路径、覆盖范围和抽取失败/缺失风险。
- 从 references/** 中提取任务相关领域知识：术语定义、类别/状态含义、可观察特征、不可观察特征、判断边界、评价口径、风险和不确定性。输出到 `artifacts/reference-knowledge.md` 工件。
- 获取或定位数据。若用户要求通过库下载数据，使用 Bash 和 `uv run --with ...` 在 workspace 的 data/ 下完成下载、缓存和转换。
- 根据任务需求和下载后的具体数据格式，将数据转换为后续工具可读取的统一格式，优先写入 data/processed/**。
- `data/processed/**`、`artifacts/reference-knowledge.md`、`artifacts/data-exploration-report.md`、`artifacts/problem-framing.md` 和 `plots/**` 是推荐的证据/审计路径，不是跨节点硬契约。后续节点应通过 `user/problem-contract.md` 和 `user/data-spec.md` 找到这些证据。
- 必须产出一份数据规范 `user/data-spec.md`，作为后续所有数据处理的锚点。后续流程中的工具构建、训练、推理、评估和 case review 都必须遵守这份数据规范。
- 数据规范必须精确定义：数据文件路径、记录粒度、样本 ID、时间轴/索引、特征列、目标列、标签映射、split 定义、缺失值规则、单位/归一化状态、允许读取的字段、禁止作为输入的泄漏字段、输出预测格式和评估所需字段。
- 对数据做 exploration：样本规模、类别/标签结构、缺失值、异常值、时间序列长度、代表性样本、边界样本、可观察形态线索、数据泄漏风险。
- 基于用户目标、参考资料和 exploration 结果，重新明确“当前真正需要解决的问题”。
- 输出 `user/problem-contract.md`，作为后续迭代的单一权威任务合约；同时输出 `user/data-spec.md`，作为后续数据读取和处理的单一权威数据合约。

`user/problem-contract.md` 是最重要的节点产物。每个章节必须给出详细、可执行、可检查的规范化定义，不能泛泛而谈。至少包含：
- Goal：明确任务目标、目标对象、输入是什么、输出是什么、哪些目标不属于本任务。
- Data specification：引用 `user/data-spec.md`，摘要说明样本粒度、字段、标签、split、允许/禁止使用字段和数据读取约束。
- Domain knowledge anchor：引用 reference 抽取和知识摘要工件，说明哪些领域知识会影响判断，哪些知识在当前数据中不可观察。
- Task framing：明确任务类型、预测/判断单元、类别或输出空间、约束条件和关键假设。
- Evaluation metrics：定义主指标、辅助指标、分组/类别级指标、case review 口径、何时认为结果有效，以及指标计算需要读取哪些字段。
- Iteration stop criteria：定义停止条件，例如达到某个指标、连续若干轮无改进、失败模式已收敛、case review 风险可接受、预算/轮次上限等。
- Required artifacts：列出后续每轮必须产出的文件路径和内容要求，例如工具注册表、解决方案计划、运行记录、预测结果、指标报告、case packets、迭代总结和 iteration-state。
- Evidence requirements：定义每个结论必须依赖哪些数据证据、工具输出、reference 证据或 case review 证据。必须特别定义 bad case 数值归因要求：case review 不能只看预测 score，必须读取原始输入并计算可审计的 per-case 数值特征；必须与 good case / prototype 对照；必须说明哪些解释有证据、哪些无法解释。
- Forbidden shortcuts and leakage risks：明确禁止读取或使用哪些字段、标签、文件名、split 泄漏、未来信息或人为答案。
- Known uncertainty and open assumptions：列出当前无法消除的不确定性，以及后续迭代必须验证或承认的假设。

不要把这一节点写成方法比较或模型优化报告。它的硬契约产物只有 `user/problem-contract.md` 和 `user/data-spec.md`；其他文件都是证据、数据或审计材料，必须被这两个锚点工件引用清楚。
