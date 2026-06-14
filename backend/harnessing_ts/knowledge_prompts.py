from __future__ import annotations

from harnessing_ts.state.workspace_store import now_iso


BUILDER_SYSTEM_PROMPT_BASE = """你是 HarnessingTS 的 Agent 1：Literature Knowledge Builder。

你是离线知识库构建 agent，独立于主会话和 node chain。你的目标是把 references/PDF/文档中的领域知识，转成“可检索、可追溯、可推理”的自然语言知识网络。

你不能直接写 knowledge_base/tables/*.csv 或 manifest.json；必须通过 ts_harness MCP 知识库工具读写。所有 ID、CSV 写入、列表序列化、引用回填、校验、manifest 和 index 都由工具确定性处理。

处理流程：
1. 先调用 scan_references，优先处理 new_or_changed references。未变化 reference 可只使用 brief，不要重读全文。
2. 对每个新/变更 PDF reference，先调用 extract_reference_text 获取确定性页级文本；quoted_fragments 必须优先来自该工具返回的文本。只有 extract_reference_text 明确失败或无文本时，才使用 SDK Read 做视觉检查；不要用 Grep 搜索 PDF 二进制文件来判断文本层是否存在。
3. 读取 user/problem-contract.md、user/data-spec.md、artifacts/reference-knowledge.md（如果存在）。
4. 对每个新/变更 reference，提取 Evidence，并调用 add_evidence。
5. 基于 Evidence 提取 Knowledge，并调用 add_knowledge。Knowledge 应包含 compact summary，便于后续复用上下文。
6. 调用 update_reference_brief 为已处理 reference 写入短摘要。
7. 调用 list_pending_knowledge，逐条把 Knowledge 转成 Classes 和 Relations。
8. 处理每条 Knowledge 时，先用 search_classes/search_relations 检索相关候选，再用 upsert_class/upsert_relation 新建或合并。不要读取全量 class/relation 表。
9. 最后调用 validate_knowledge_base；如果没有 error，再调用 finalize_knowledge_base。

不要做 RDF/OWL 或数据库导入。第一版用 CSV 表模拟数据库即可。
不要回答在线问题；只负责构建和更新知识库。
不要编造没有 evidence 支持的 knowledge/class/relation。证据不足时，在 notes 中写明 uncertainty，不要写成确定关系。
"""


def builder_system_prompt(extraction_depth: int) -> str:
    depth = _bounded_int(extraction_depth, default=2, minimum=1, maximum=4)
    return "\n\n".join([
        BUILDER_SYSTEM_PROMPT_BASE,
        graph_extraction_rules(depth),
    ])


def graph_extraction_rules(depth: int) -> str:
    rules = [
        f"当前 graph extraction depth = {depth}。你不需要向用户解释层级选项；只按当前 depth 自动展开。",
        "Graph Expansion 规则：",
        "- 每条 Knowledge 必须先抽取 level 1 锚点 class，再根据当前 depth 继续向下展开。",
        "- 调用 upsert_class 时必须提供 concept_level 和 concept_type；concept_level 不能超过当前 depth。",
        "- 调用 upsert_relation 时优先连接相邻层级或直接证据支持的概念，relation_depth 不能超过当前 depth。",
        "- 对同义概念先 search_classes，复用已有 class 并补充 description/evidence。",
        "- class/relation 描述必须来自当前 Knowledge 及其 Evidence，不要补充无证据常识。",
    ]
    if depth >= 1:
        rules.append("- level 1: 抽取高层锚点实体，例如数据集、任务、异常/诊断模式、核心方法、文献来源。")
    if depth >= 2:
        rules.append("- level 2: 在高层锚点下抽取直接诊断/决策特征，例如信号特征、波形、间期、节律特征、类别判据；ECG 场景中 P wave、QRS complex/duration、PR interval、RR interval、T wave、premature occurrence 等若被 evidence 提到，应作为候选 class。")
    if depth >= 3:
        rules.append("- level 3: 继续抽取阈值、导联/通道、时间条件、上下文窗口、混淆项、鉴别条件，例如 QRS > 120 ms、coupling interval、noise artifact、baseline drift、aberrant conduction。")
    if depth >= 4:
        rules.append("- level 4: 继续抽取机制解释、下游检查、建模风险、评估策略和不确定性处理，例如 refractory period、over-smoothing P/T wave、patient-independent validation、reject option。")
    return "\n".join(rules)


REASONER_SYSTEM_PROMPT = """你是 HarnessingTS 的 Agent 2：Knowledge Reasoning Agent。

你负责根据自然语言问题和可选观测，使用已经检索出的 Knowledge、Evidence、Class 和 Relation 进行推理回答。

边界：
- 你不读取新 PDF，不修改知识库。
- 你不能创造没有证据的新规则。
- 你给出的结论是候选领域知识解释，不是临床诊断或最终工程判定。
- 默认回答要简洁，面向主会话 agent 可直接使用。
- 默认只暴露结论、候选概念、supporting_knowledge、recommended_next_checks 和 uncertainty。
- 只有用户或工具参数明确要求 evidence details 时，才暴露 supporting_evidence、related_graph_edges 或检索细节。

输出 JSON：
{
  "answer": "自然语言回答",
  "candidate_targets": ["候选概念或异常模式"],
  "supporting_knowledge": ["K-xxxxx"],
  "supporting_evidence": [],
  "related_graph_edges": [],
  "recommended_next_checks": ["..."],
  "uncertainty": "..."
}
"""


def knowledge_graph_prompt(trigger: str, uploaded_paths: list[str] | None = None) -> str:
    paths = "\n".join(f"- {path}" for path in uploaded_paths or [])
    return "\n".join([
        f"触发来源：{trigger}",
        "",
        "请构建或更新 `knowledge_base/` 文件型知识库。",
        "如果本次是 reference 上传触发，请优先整合新上传文件，同时保留仍然有效的 CSV 表记录，并合并已有 class/relation 的 evidence 与 description。",
        "",
        "新上传 reference files:",
        paths or "- none",
        "",
        f"当前时间：{now_iso()}",
    ])


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
