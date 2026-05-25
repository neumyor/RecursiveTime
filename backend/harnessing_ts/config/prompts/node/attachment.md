# Node Startup Context
node_type: {node_type}
{input_summary_block}

## Required Finish
完成后输出完整、极短、合法 JSON：harnessControl({ action: 'finish_node', success, summary, goalMet?, outputPaths? })。
不要在 harnessControl JSON 中放长文本；避免输出被截断导致后端无法推进。
