phase: setup
next: iterative-solving
purpose: 根据用户输入和参考资料获取并处理数据，通过数据 exploration 明确当前要解决的问题，并给出整个流程的 contract。

requires:
- 用户原始需求
- references/**
- data/raw/** 或用户指定数据来源

produces:
- user/problem-contract.md
- user/data-spec.md
