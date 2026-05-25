## Harness Control Protocol
完成本 node 时必须在最后追加一个完整、极短、合法的 JSON fenced block。不要把长摘要或长 outputPaths 放进控制 JSON；长内容写入报告文件，控制 JSON 只放短摘要和关键锚点路径。
不要输出 DSML、tool_calls、invoke 或任何供应商私有 tool-call 标记；这里只能输出普通文本和下面的 JSON fenced block。

```json
{"harnessControl":{"action":"finish_node","success":true,"summary":"short summary","goalMet":false,"outputPaths":["reports/iterations/001-summary.md","user/iteration-state.md"]}}
```

如果无法完成，success=false，并在 summary 里说明阻塞原因。
