# Node Startup Context
node_type: {node_type}
{input_summary_block}

## Required Finish
完成后调用 MCP 工具 `mcp__ts_harness__finish_node`。
不要输出 JSON 控制块；长摘要必须写入报告文件，MCP 参数只放短摘要、关键路径和结构化流转字段。
如果当前 node 是 `iterative-solving`，必须在 `finish_node` 中用 `loopDecision` 和 `nextNode` 明确声明继续下一轮还是进入 `final-summary`。
