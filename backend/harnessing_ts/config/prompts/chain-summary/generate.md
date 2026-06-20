# 生成任务

请生成 HarnessingTS 当前 workspace 的思维链总结。

## Workspace Manifest

```json
{manifest_json}
```

## 重点回答

1. 每个 iteration 中提出了哪些方法或候选，保留或放弃的原因是什么。
2. 每轮测试结果如何，哪些指标提升或退化。
3. 哪些样本、bad case 或可视化启发了下一轮 iteration。
4. 本轮实验证据与参考领域知识如何共同形成下一轮可验证的优化决策。

## 本次输出约束

- `metricSeries.values[].iteration` 必须使用 iteration 编号或 ID，`label` 只备注本轮最佳候选。
- 每轮 `methods` 与 `methodResults` 数量、顺序和方法名必须一一对应。
- `uncertainty` 最多六条，每条一句。
- 不生成轮次摘要字段。
- 生成前必须实际读取相关知识文件或知识图谱内容。
- 使用内置 `Write` 将完整 JSON 写入 `{draft_path}`。
- 写入完成后只回复一句简体中文确认。
