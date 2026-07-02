phase: iteration
next: final-summary
purpose: 根据任务契约每轮提出 k 个候选解决方案，分别分配子智能体做可行性测试与案例复盘，再统一综合证据，选择本轮落盘执行对象或下一轮迭代方向；k 必须通过实时运行参数获取；必须先生成候选审查与案例复盘，再生成迭代总结，最后判断结束迭代或继续下一轮优化。

requires:
- user/problem-contract.md
- user/data-spec.md
- tools/**
- reports/iterations/**
- user/iteration-state.md

produces:
- tools/**
- runs/iterations/<iteration-id>/**
- reports/iterations/<iteration-id>-candidate-review.md
- reports/iterations/<iteration-id>-case-review.md
- reports/iterations/<iteration-id>-summary.md
- user/iteration-state.md
