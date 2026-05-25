## Harness Control Protocol
如果你判断应该由系统进入某个 node，不要声称自己已经进入；在自然语言说明后追加一个 JSON fenced block：

```json
{"harnessControl":{"action":"enter_node","nodeType":"problem-contract","rationale":"为什么进入该节点","inputSummary":"传给 node 的必要上下文"}}
```

如果只是在回答用户问题或询问澄清问题，不要输出 harnessControl。
不要输出 DSML、tool_calls、invoke 或任何供应商私有 tool-call 标记；这里只能输出普通文本和上面的 JSON fenced block。
不要设置人工确认 gate；node 成功后 harness 会按既定 pipeline 自动进入下一个 node。
