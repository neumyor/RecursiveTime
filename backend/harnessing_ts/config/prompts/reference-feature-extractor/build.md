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

严格读取这些文件并完成 `tools/reference-feature-extractor/**`。先写 `evidence-map.json` 和 `feature-plan.json`，再实现 extractor。构建和验收必须至少使用一个当前 workspace 的真实样本输入：按 `user/data-spec.md` 从真实数据源抽取样本，转换成 extractor stdin JSON，写入 `test-cases.json`，在该项用 `source.type="real_sample"` 和已存在的 workspace 相对 `source.path` 记录原始路径，并可额外记录 case id、split/fold 或行号等可审计来源，然后用该真实样本运行确定性测试。完成后必须写 `evaluation-report.json`，包含真实样本逐 case 输出摘要、featureStatusCounts、至少一个 control/reference case 和 summary.controlCaseWarnings。合成样本只能作为补充 smoke test，不能替代真实样本。若任务定义、reference 或真实样本读取条件不足以构建任何可计算 feature，必须明确失败，不要生成基于常识的占位规则。
