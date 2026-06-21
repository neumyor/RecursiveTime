## Ablation Variant V3: No Knowledge Graph

本变体禁止使用知识图谱和 reference-derived knowledge：

- 不得调用 `query_knowledge`；该工具不会提供。
- 不得读取 `references/**`、`knowledge_base/**`、`artifacts/reference-knowledge.md` 或其他 reference 摘要来形成任务知识。
- 不生成 `artifacts/reference-knowledge.md` 或 `knowledge_base/domain-brief.md`。
- problem contract 和 data spec 只能依据用户明确需求、原始数据 exploration、可观察字段和评价约束建立。
- 对基础 guidance 中要求读取 references、构建 reference knowledge 或查询知识图谱的条款，以本 overlay 为准。
