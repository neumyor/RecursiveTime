本节点只在迭代优化结束后执行，用于总结全过程和最终结果。

必须完成：
- 读取 problem contract、iteration-state、每轮 iteration summary、runs/iterations/** 和相关 timeline。
- 读取 `user/data-spec.md` 和 `tools/**`，确认最终方案是否遵守数据规范、工具接口和运行记录。
- 总结完整优化历程：每轮做了什么、为什么做、结果如何、如何反思、下一轮如何调整。
- 给出最终工具使用方案：工具清单、调用顺序、证据规则、冲突处理、不确定性处理和人工复核边界。
- 给出最终结果：核心指标、关键案例、失败模式、适用范围和不可支持的结论。
- 明确哪些结论来自真实工件和运行记录，不要编造不存在的实验。
- 输出 `reports/final-summary.md` 和 `user/final-solution.md`。最终指标、关键结果和失败模式写入 `reports/final-summary.md` 的固定章节，不再单独要求 `reports/final-result.md`。

如果 `user/iteration-state.md` 显示仍不建议退出，则不要伪造最终结果；应在 final summary 中明确当前不应结束，并列出需要继续迭代的原因。
