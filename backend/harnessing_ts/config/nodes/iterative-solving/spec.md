phase: iteration
next: final-summary
purpose: 根据 contract 每轮提出 k 个候选解决方案，分别分配 subagent 做可行性测试与 case review，再统一综合证据，选择本轮落盘执行对象或下一轮迭代方向；k 必须通过实时 runtime settings 获取；必须先生成候选审查与 case review，再生成 iteration summary，最后判断结束迭代或继续下一轮优化。

requires:
- user/problem-contract.md
- user/data-spec.md
- tools/**
- reports/iterations/**
- user/iteration-state.md
- knowledge_base/**

produces:
- tools/**
- runs/iterations/<iteration-id>/**
- reports/iterations/<iteration-id>-case-review.md
- reports/iterations/<iteration-id>-summary.md
- user/iteration-state.md
