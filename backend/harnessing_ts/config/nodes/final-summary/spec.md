phase: summary
next: none
purpose: 当迭代优化结束后，总结整个优化历程、最终工具使用方案、最终结果和系统边界。

requires:
- user/problem-contract.md
- user/data-spec.md
- user/iteration-state.md
- reports/iterations/**
- runs/iterations/**
- tools/**
- logs/timeline.jsonl

produces:
- reports/final-summary.md
- user/final-solution.md
