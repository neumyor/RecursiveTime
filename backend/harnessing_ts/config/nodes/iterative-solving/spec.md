phase: iteration
next: final-summary
purpose: 根据 contract 每轮只构建并尝试一种新方法，或将此前已落盘工具进行一种明确组合；先把方法标准化为 tools/ 下可调用工具，再执行和分析结果；必须先生成 case review，再生成 iteration summary，最后判断结束迭代或继续下一轮优化。

requires:
- user/problem-contract.md
- user/data-spec.md
- tools/**
- reports/iterations/**
- user/iteration-state.md

produces:
- tools/**
- runs/iterations/<iteration-id>/**
- reports/iterations/<iteration-id>-case-review.md
- reports/iterations/<iteration-id>-summary.md
- user/iteration-state.md
