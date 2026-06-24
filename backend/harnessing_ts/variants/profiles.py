from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any


VARIANT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class AblationVariant:
    id: str
    name: str
    description: str
    node_chain: bool = True
    knowledge_graph: bool = True
    reference_knowledge: bool = True
    knowledge_to_tools: bool = True
    independent_subagents: bool = True
    case_review: bool = True
    random_search: bool = False
    max_iterations: int | None = None
    main_prompt: str | None = None
    node_prompts: dict[str, str] = field(default_factory=dict)
    node_purposes: dict[str, str] = field(default_factory=dict)

    @property
    def direct_main_tool_use(self) -> bool:
        return not self.node_chain

    @property
    def reference_feature_extractor(self) -> bool:
        """The reference feature extractor is available iff the
        `knowledge-to-tools` node runs and produces a validated tool.
        V7 (and any future variant that disables the node) propagates
        from `knowledge_to_tools`."""
        return self.knowledge_to_tools

    def prompt_overlay(self, scope: str) -> str:
        relative = self.main_prompt if scope == "main" else self.node_prompts.get(scope)
        if not relative:
            return ""
        return (VARIANT_DIR / "prompts" / relative).read_text(encoding="utf-8").strip()

    def public_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "capabilities": {
                "nodeChain": self.node_chain,
                "knowledgeGraph": self.knowledge_graph,
                "referenceKnowledge": self.reference_knowledge,
                "knowledgeToTools": self.knowledge_to_tools,
                "referenceFeatureExtractor": self.reference_feature_extractor,
                "independentSubagents": self.independent_subagents,
                "caseReview": self.case_review,
                "randomSearch": self.random_search,
                "maxIterations": self.max_iterations,
                "directMainToolUse": self.direct_main_tool_use,
            },
        }

    def node_requires(self, node_type: str, paths: tuple[str, ...]) -> list[str]:
        values = list(paths)
        if not self.reference_knowledge and node_type == "problem-contract":
            values = [value for value in values if "references/" not in value]
        if not self.knowledge_to_tools and node_type == "knowledge-to-tools":
            return []
        return values

    def node_purpose(self, node_type: str, default: str) -> str:
        return self.node_purposes.get(node_type, default)

    def node_produces(self, node_type: str, paths: tuple[str, ...]) -> list[str]:
        values = list(paths)
        if not self.case_review and node_type == "iterative-solving":
            values = [value for value in values if "case-review" not in value]
        if not self.knowledge_to_tools and node_type == "knowledge-to-tools":
            return []
        return values


VARIANTS: dict[str, AblationVariant] = {
    "V0": AblationVariant(
        id="V0",
        name="Full HarnessingTS",
        description="Complete HarnessingTS with the full node, knowledge, candidate, review, tool, memory, and adaptive-stop workflow.",
    ),
    "V1": AblationVariant(
        id="V1",
        name="Single-Agent Tool Use",
        description="One coding-agent session with data, code, and tool access; no node chain, knowledge graph, candidate subagents, structured case review, or iteration state.",
        node_chain=False,
        knowledge_graph=False,
        reference_knowledge=False,
        knowledge_to_tools=False,
        independent_subagents=False,
        case_review=False,
        main_prompt="v1-single-agent.md",
    ),
    "V2": AblationVariant(
        id="V2",
        name="Random Search",
        description="Samples candidates from a fixed method and parameter catalog under the same candidate budget, then selects the best validation result.",
        random_search=True,
        node_prompts={"iterative-solving": "v2-random-search.md"},
        node_purposes={"iterative-solving": "按后端随机 sampler 返回的 k 个固定目录配置执行相同预算的候选测试，选择主验证指标最佳结果并保留完整审计记录。"},
    ),
    "V3": AblationVariant(
        id="V3",
        name="No Knowledge Graph",
        description="Full workflow without query_knowledge or reference-derived knowledge; decisions use contracts, history, results, and data evidence only.",
        knowledge_graph=False,
        reference_knowledge=False,
        knowledge_to_tools=False,
        node_prompts={
            "problem-contract": "v3-no-knowledge-problem-contract.md",
            "iterative-solving": "v3-no-knowledge-iterative.md",
        },
        node_purposes={
            "problem-contract": "仅依据用户需求和数据 exploration 建立 problem contract 与 data spec，不使用 references 或知识图谱。",
            "iterative-solving": "仅依据 contract、历史运行和数据证据生成候选、执行评估与错误归因，不使用 reference knowledge。",
        },
    ),
    "V4": AblationVariant(
        id="V4",
        name="No Independent Subagents",
        description="Keeps k candidates and the same execution budget, but the iterative agent implements, tests, and reviews candidates sequentially without Task subagents.",
        independent_subagents=False,
        node_prompts={"iterative-solving": "v4-no-subagents.md"},
        node_purposes={"iterative-solving": "保留相同 k 和执行预算，由当前 iterative agent 顺序实现、测试和审查所有候选，不创建独立 Task subagent。"},
    ),
    "V5": AblationVariant(
        id="V5",
        name="No Case Review",
        description="Keeps candidate generation, subagent tests, and iteration, but removes per-case analysis, statistical attribution, and case visualization.",
        case_review=False,
        node_prompts={
            "iterative-solving": "v5-no-case-review.md",
            "final-summary": "v5-no-case-review-final.md",
        },
        node_purposes={"iterative-solving": "保留候选和迭代，只依据聚合验证指标、执行状态和成本选择方案，不执行任何 case-level review 或可视化。"},
    ),
    "V6": AblationVariant(
        id="V6",
        name="One-Shot Harness",
        description="Keeps contracts, knowledge, candidate subagents, and case review, but permits exactly one iterative-solving round before final summary.",
        max_iterations=1,
        node_prompts={"iterative-solving": "v6-one-shot.md"},
        node_purposes={"iterative-solving": "执行唯一一轮完整 HarnessingTS 候选、subagent 和 case review，随后强制进入 final-summary。"},
    ),
    "V7": AblationVariant(
        id="V7",
        name="No Knowledge-to-Tools Node",
        description="Full workflow without the knowledge-to-tools node: the main session never builds a deterministic reference feature extractor, the chain skips the new node, and case review must rely on other numeric tools and evidence.",
        knowledge_to_tools=False,
        node_prompts={
            "iterative-solving": "v7-no-knowledge-to-tools.md",
        },
        node_purposes={
            "knowledge-to-tools": "本变体跳过 knowledge-to-tools 节点；主会话不在该节点构建 reference feature extractor。",
        },
    ),
}


def get_variant(value: str) -> AblationVariant:
    variant_id = value.strip().upper()
    try:
        return VARIANTS[variant_id]
    except KeyError as exc:
        choices = ", ".join(VARIANTS)
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; expected one of: {choices}.") from exc


def resolve_variant() -> AblationVariant:
    return get_variant(os.getenv("TS_HARNESS_VARIANT", "V0"))
