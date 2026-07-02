phase: setup
next: iterative-solving
purpose: 在主会话中，根据问题契约、数据规范、参考资料目录以及知识图谱（若已构建），并结合主会话的领域常识，生成、迭代并通过后端校验的确定性参考特征提取器。校验通过后，`tools/reference-feature-extractor/**` 才能被迭代求解节点的案例复盘视为可用数值证据来源。

requires:
- user/problem-contract.md
- user/data-spec.md
- references/**
- knowledge_base/**
- artifacts/reference-knowledge.md
- artifacts/knowledge-graph.json（若已构建）

produces:
- tools/reference-feature-extractor/**
- tools/reference-feature-extractor/evidence-map.json
- tools/reference-feature-extractor/feature-plan.json
- tools/reference-feature-extractor/evaluation-report.json
- state/reference-feature-build.json
