# Build request

请根据当前 workspace 生成或完整重建 reference feature extractor。

任务定义文件：
```json
{task_files_json}
```

Reference 文件：
```json
{references_json}
```

严格读取这些文件并完成 `tools/reference-feature-extractor/**`。若任务定义或 reference 不足以构建任何可计算 feature，必须明确失败，不要生成基于常识的占位规则。
