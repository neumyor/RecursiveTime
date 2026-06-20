```json
{
  "title": "string",
  "generatedAt": "ISO timestamp or empty",
  "overview": "string",
  "metricSeries": [
    {
      "name": "metric name",
      "unit": "optional unit",
      "direction": "higher|lower|neutral",
      "values": [
        {"iteration": "iteration number or id", "label": "best candidate/method label", "value": 0.0}
      ]
    }
  ],
  "iterations": [
    {
      "iterationId": "string",
      "methods": [
        {"name": "string", "hypothesis": "string", "artifactPath": "optional path"}
      ],
      "testResults": [
        {"metric": "string", "value": "string", "evidencePath": "optional path", "interpretation": "string"}
      ],
      "methodResults": [
        {
          "methodName": "must match methods[].name",
          "metric": "primary/core metric",
          "value": "string",
          "evidencePath": "optional path",
          "interpretation": "string"
        }
      ],
      "sampleInspirations": [
        {
          "sampleId": "string",
          "visualizationPath": "workspace relative image path or empty",
          "interpretation": "string",
          "nextIterationImpact": "string"
        }
      ],
      "nextDecision": {
        "decision": "优化方向及选择原因",
        "iterationEvidence": "触发决策的指标、失败案例或对照实验",
        "domainKnowledge": [
          {
            "knowledge": "具体领域规律",
            "sourcePath": "workspace 相对路径",
            "guidance": "该规律如何改变下一轮设计或验证"
          }
        ],
        "actions": [
          {
            "action": "可执行动作",
            "expectedEffect": "预期改善的机制或指标",
            "validation": "验证方式"
          }
        ]
      }
    }
  ],
  "artifacts": [{"path": "workspace relative path", "role": "string"}],
  "uncertainty": ["string"]
}
```
