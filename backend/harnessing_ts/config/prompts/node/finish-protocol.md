## Harness Control Protocol
完成本 node 时，不要输出 JSON 控制块，也不要声称系统状态已经完成迁移。

你必须在完成必要工件后调用 MCP 工具 `mcp__ts_harness__finish_node`，参数为：
- `success`: 本 node 是否成功完成。
- `summary`: 极短摘要，长内容必须写入报告文件。
- `goalMet`: 如果本 node 能判断目标是否达成，则给出布尔值；否则可省略。
- `nextNode`: 结构化节点流转决策。普通节点通常省略，由后端按 node spec 的 `next` 推进；`iterative-solving` 必须填写：
  - `iterative-solving`: 继续下一轮迭代。
  - `final-summary`: 停止迭代并进入最终总结。
  - `none`: 停止 pipeline，不进入后续节点。
- `loopDecision`: 仅 `iterative-solving` 使用。继续迭代填 `continue`，退出迭代填 `exit`。
- `outputPaths`: 本 node 的关键产物路径，只列锚点文件。

控制模式由后端决定：
- `auto`: MCP 请求会被 harness 自动放行并推进 pipeline。
- `manual`: MCP 请求会被写入 pending control，等待用户在前端批准或拒绝。

如果无法完成，调用 `finish_node` 时设置 `success=false`，并在 `summary` 中说明阻塞原因。
`user/iteration-state.md`、summary、case review 等文件是审计工件，不是主控制通道；但 iterative-solving 的 `finish_node` 参数必须与 `user/iteration-state.md` 开头机器块中的 `recommend_exit` 一致。后端会拒绝 `recommend_exit: false` 却进入 `final-summary`，或 `recommend_exit: true` 却继续迭代的请求。
不要输出 DSML、tool_calls、invoke、fenced JSON 或供应商私有工具调用标记。
