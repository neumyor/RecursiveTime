本节点由主会话直接在当前 workspace 中完成，目标是在已有 problem contract、data spec、references/** 与（若已构建的）知识图谱基础上，生成、迭代并通过后端强校验的**确定性** reference feature extractor。生成完成后，iterative-solving 的 case review 才能用 `mcp__ts_harness__extract_reference_features` 与 `mcp__ts_harness__inspect_reference_feature_extractor` 把工具的输出视为可审计的 per-case 数值证据。

主会话是唯一构建者：后端不再提供独立 reference feature builder 子会话。所有写入、运行、调试都由主会话通过本节点的 native 工具完成；后端只在主会话调用 `mcp__ts_harness__validate_reference_feature_extractor` 时执行最终的强校验。

核心约束：
- 所有判断必须落到 `user/problem-contract.md`、`user/data-spec.md` 与 `references/**` 的真实文本上。不得用 LLM 常识、模型默认或训练经验补充任何 feature、阈值、judgment 或 domain 规则；若这些材料没有给出当前 feature 的依据，必须把该 feature 标为 `indeterminate` 并把判定理由写入 README。
- 若知识图谱已构建并通过 `knowledgeGraphReady=true`，应通过 `mcp__ts_harness__query_knowledge` 获取领域知识，候选 feature、judgment 与 reference 引用应与知识图谱中的定义保持一致；不得把 `knowledge_base/tables/*.csv`、`knowledge_base/indexes/**` 或 `knowledge_base/cache/**` 当成普通读取入口直接消费。
- 若知识图谱尚未构建或不可用，主会话可结合 `references/**` 文本与自身对任务领域的常识，定义 reference 规则；但 evidence 必须仍指向 `references/**` 中的具体原文（路径、章节/页码与短引用），不得伪造引用。
- 生成的 extractor 必须是纯确定性的：禁止网络、LLM、随机数、系统时间、外部进程、训练、在线拟合或隐式可变状态。相同 JSON 输入必须产生字节级一致的 JSON 输出。
- extractor.py 必须从 stdin 读取一个 JSON 值，只向 stdout 写一个 JSON 对象；错误写 stderr 并以非零状态退出。
- extractor 的输入必须严格遵守 `user/data-spec.md`；输出必须包含 `schemaVersion: "1.0"`、`features` 和 `warnings` 三个顶层字段。
- 每个输出 feature 必须包含 `name`、`value`、`unit`、`judgment`、`evidence`；`judgment` 必须包含 `status`（normal/abnormal/indeterminate/not_applicable）、`label` 与可审计的 `rule`。
- 只允许写入 `tools/reference-feature-extractor/**`，不得修改 task contract、data spec、references、knowledge_base/** 或其他工具。
- 不得删除或覆盖上一轮已经验证通过的 `tools/reference-feature-extractor/**`，除非主会话主动决定重新生成。删除后端会拒绝再次注入 MCP 工具。

必须完成：
- 调用 `mcp__ts_harness__get_runtime_settings` 读取最新运行时参数（虽然本节点不直接用 k，但保持与 iterative-solving 一致的设置读取习惯）。
- 阅读 `user/problem-contract.md` 与 `user/data-spec.md`，明确任务目标、输入输出、评价口径和 case review 要求。
- 阅读 `references/**` 中与本任务相关的章节，记录每个 feature 的 evidence（reference 路径、章节或页码、关键短引用）。DOCX 优先读取同名 `.docx.txt`；PDF 用 Claude Code SDK 的原生 `Read` 工具；其他文本可直接读取。
- 若知识图谱已构建，对关键 feature 或 judgment 调一次 `mcp__ts_harness__query_knowledge` 验证领域定义与 reference 文本一致；只有当知识图谱的某条结论与本节点已写出的 feature 直接相关时才需要查询，避免无意义上下文消耗。
- 规划候选 feature 集合：每个 feature 至少对应一条 reference 证据；feature 之间应正交、可独立计算；judgment 阈值必须可被 reference 原文或 `user/data-spec.md` 支持。
- 在 `tools/reference-feature-extractor/` 下创建：
  - `extractor.py`：纯确定性 Python 程序；满足 AST 白名单、禁止调用、确定输入输出。
  - `manifest.json`：`schemaVersion="1.0"`、`entrypoint="tools/reference-feature-extractor/extractor.py"`、`inputSchema`、`outputSchema` 与 `features` 数组（每条 feature 含 `name`、`description` 与非空 `evidence`）。
  - `reference-rules.json`：`features` 数组；每条 rule 必须包含与 manifest 完全一致的 `name`、自然语言 `computation`、非空 `judgments` 数组与非空 `evidence` 数组。
  - `README.md`：详细说明用途、适用范围、reference 范围、输入 schema、输出 schema、调用方法、feature/rule 列表、不可观察条件、风险与限制。
  - `test-cases.json`：数组，每项含 `input`，尽量包含完整 `expected`；后端会执行至少一次重复运行以验证字节级一致。
- 使用 `Bash` 在 workspace 根目录通过 `uv run python tools/reference-feature-extractor/extractor.py < input.json` 至少试运行一次，确保能正确从 stdin 读取并向 stdout 写出 JSON。
- 调用 MCP `mcp__ts_harness__validate_reference_feature_extractor` 触发后端强校验：
  - 输入可携带 `{runTests: true}` 强制后端运行确定性测试；默认也会运行。
  - 失败时返回的 error message 会指明具体缺陷（缺失文件、manifest schema、reference 引用、AST 禁用项、确定性测试等）；主会话必须根据 error 修订并重试。
  - 成功后主会话可以继续；iterative-solving 在 case review 时才把工具视为可用。
- 完成全部工件且后端校验通过后，调用 `mcp__ts_harness__finish_node` 提交本节点：
  - `success=true` 表示本节点目标已达成；`summary` 用一两句话说明已写出的工件与后端校验结果。
  - `outputPaths` 必须包含 `tools/reference-feature-extractor/{extractor.py,manifest.json,reference-rules.json,README.md,test-cases.json}` 与 `state/reference-feature-build.json`。
  - `nextNode` 可以省略，由后端按 node spec 推进到 `iterative-solving`；若决定终止迭代链，可显式设为 `none`。

注意：
- 本节点使用与 `problem-contract` 相似的 native 工具集：所有写入、运行、调试都在主会话内完成，没有独立 subagent 或后台任务。
- 后端的强校验决定了 `extract_reference_features` 与 `inspect_reference_feature_extractor` 是否被注入；不要试图通过删除 `tools/reference-feature-extractor/**` 之外的路径绕过校验。
- 如果需要彻底重新生成（删除旧 extractor 再写新的），应先显式删除 `tools/reference-feature-extractor/` 下的所有文件，再重新创建并重新调用 validate。
- 不要在 `extractor.py` 中读取 `data/raw/**`、`knowledge_base/**` 或网络资源；输入只能来自调用方传入的 JSON。
- 当 reference 不足以支撑某个 feature 的判断时，必须保留 feature 但在 extractor 内返回 `indeterminate` 的 judgment，并在 README 中记录不可观察条件；不要因为 reference 不够就删掉 feature 跳过。
- 当本节点处于 `iterative-solving` 已被执行过、且 case review 已经依赖过该 extractor 的情况下，需要重新构建时必须在 README 中说明变更点，并在最终 summary 中标注行为变化；后端不接受“悄悄”重写已验证 extractor。
- 本节点与 `problem-contract` 一样属于 setup 阶段，不会消耗 `iterativeCandidateCount`；其输出只是为 case review 提供数值工具。
- 完成本节点只能调用 MCP `mcp__ts_harness__finish_node`。不要输出 `harnessControl` JSON，也不要期望后端从文件产物推断节点完成。
