from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any


VARIANT_DIR = Path(__file__).resolve().parent

FEATURE_DESCRIPTIONS: dict[str, str] = {
    "NOD": "HarnessingTS node chain",
    "KGR": "file-backed reference knowledge graph",
    "RQA": "direct reference QA agent over references/**",
    "KTL": "knowledge-to-tools node and reference feature extractor",
    "CRV": "case-level review and attribution",
    "SUB": "independent Task subagents",
    "ADA": "adaptive iterative solving",
    "DIR": "direct single-agent tool-use baseline",
}
FEATURE_ORDER = ("NOD", "KGR", "RQA", "KTL", "CRV", "SUB", "ADA")
DIRECT_FEATURE = "DIR"
DEFAULT_VARIANT_ID = "NOD-KGR-KTL-CRV-SUB-ADA"
LEGACY_ALIASES: dict[str, str] = {
    "V0": DEFAULT_VARIANT_ID,
    "V1": "NOD-RQA-KTL-CRV-SUB-ADA",
    "V2": "NOD-RQA-KTL-SUB-ADA",
    "V3": "NOD-RQA-CRV-SUB-ADA",
    "V4": "NOD-RQA-SUB-ADA",
    "V5": DIRECT_FEATURE,
}


@dataclass(frozen=True)
class AblationVariant:
    id: str
    name: str
    description: str
    features: frozenset[str]
    node_chain: bool = True
    knowledge_graph: bool = True
    knowledge_query: bool = True
    knowledge_query_source: str = "graph"
    reference_knowledge: bool = True
    knowledge_to_tools: bool = True
    independent_subagents: bool = True
    case_review: bool = True
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
        Variants that disable the node propagate from
        `knowledge_to_tools`."""
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
            "features": sorted(self.features, key=_feature_sort_key),
            "capabilities": {
                "nodeChain": self.node_chain,
                "knowledgeGraph": self.knowledge_graph,
                "knowledgeQuery": self.knowledge_query,
                "knowledgeQuerySource": self.knowledge_query_source,
                "referenceKnowledge": self.reference_knowledge,
                "knowledgeToTools": self.knowledge_to_tools,
                "referenceFeatureExtractor": self.reference_feature_extractor,
                "independentSubagents": self.independent_subagents,
                "caseReview": self.case_review,
                "maxIterations": self.max_iterations,
                "directMainToolUse": self.direct_main_tool_use,
            },
        }

    def node_requires(self, node_type: str, paths: tuple[str, ...]) -> list[str]:
        values = list(paths)
        if not self.reference_knowledge and node_type == "problem-contract":
            values = [value for value in values if "references/" not in value]
        if not self.knowledge_graph:
            values = [
                value
                for value in values
                if not value.startswith("knowledge_base/")
                and value != "artifacts/reference-knowledge.md"
                and not value.startswith("artifacts/knowledge-graph.json")
            ]
        if not self.knowledge_to_tools and node_type == "knowledge-to-tools":
            return []
        return values

    def node_purpose(self, node_type: str, default: str) -> str:
        return self.node_purposes.get(node_type, default)

    def node_enabled(self, node_type: str) -> bool:
        if node_type == "knowledge-to-tools" and not self.knowledge_to_tools:
            return False
        return True

    def node_next(self, _node_type: str, default: str | None) -> str | None:
        if default == "knowledge-to-tools" and not self.knowledge_to_tools:
            return "iterative-solving"
        return default

    def node_produces(self, node_type: str, paths: tuple[str, ...]) -> list[str]:
        values = list(paths)
        if not self.case_review and node_type == "iterative-solving":
            values = [value for value in values if "case-review" not in value]
        if not self.knowledge_to_tools and node_type == "knowledge-to-tools":
            return []
        return values


def _feature_sort_key(feature: str) -> int:
    if feature == DIRECT_FEATURE:
        return -1
    return FEATURE_ORDER.index(feature)


def _canonicalize_features(features: set[str]) -> str:
    if features == {DIRECT_FEATURE}:
        return DIRECT_FEATURE
    return "-".join(feature for feature in FEATURE_ORDER if feature in features)


def _parse_features(value: str) -> frozenset[str]:
    raw = value.strip().upper()
    if not raw:
        raise RuntimeError(
            f"Invalid TS_HARNESS_VARIANT={value!r}; expected a feature-code profile such as {DEFAULT_VARIANT_ID}."
        )
    if raw in LEGACY_ALIASES:
        raw = LEGACY_ALIASES[raw]
    parts = [part.strip() for part in raw.split("-") if part.strip()]
    features = set(parts)
    unknown = sorted(features - set(FEATURE_DESCRIPTIONS))
    if unknown:
        known = ", ".join(FEATURE_DESCRIPTIONS)
        raise RuntimeError(
            f"Invalid TS_HARNESS_VARIANT={value!r}; unknown feature code(s): {', '.join(unknown)}. "
            f"Known feature codes: {known}."
        )
    if len(parts) != len(features):
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; duplicate feature codes are not allowed.")
    _validate_feature_combination(value, features)
    return frozenset(features)


def _validate_feature_combination(value: str, features: set[str]) -> None:
    if DIRECT_FEATURE in features and features != {DIRECT_FEATURE}:
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; DIR cannot be combined with other features.")
    if features == {DIRECT_FEATURE}:
        return
    if "NOD" not in features:
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; non-DIR variants must include NOD.")
    if {"KGR", "RQA"} <= features:
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; KGR and RQA are mutually exclusive.")
    if not ({"KGR", "RQA"} & features):
        raise RuntimeError(f"Invalid TS_HARNESS_VARIANT={value!r}; NOD variants must include exactly one of KGR or RQA.")
    node_only = {"KTL", "CRV", "SUB", "ADA"}
    if node_only & features and "NOD" not in features:
        raise RuntimeError(
            f"Invalid TS_HARNESS_VARIANT={value!r}; {', '.join(sorted(node_only & features))} require NOD."
        )


def _variant(
    canonical_id: str,
    *,
    name: str,
    description: str,
    **kwargs: Any,
) -> AblationVariant:
    features = _parse_features(canonical_id)
    return AblationVariant(
        id=_canonicalize_features(set(features)),
        name=name,
        description=description,
        features=features,
        node_chain="NOD" in features,
        knowledge_graph="KGR" in features,
        knowledge_query=("KGR" in features or "RQA" in features),
        knowledge_query_source="graph" if "KGR" in features else ("references" if "RQA" in features else "none"),
        reference_knowledge=("NOD" in features and "DIR" not in features),
        knowledge_to_tools="KTL" in features,
        independent_subagents="SUB" in features,
        case_review="CRV" in features,
        **kwargs,
    )


VARIANTS: dict[str, AblationVariant] = {
    DEFAULT_VARIANT_ID: _variant(
        DEFAULT_VARIANT_ID,
        name="Full HarnessingTS",
        description="Complete HarnessingTS with the full node, knowledge, candidate, review, tool, memory, and adaptive-stop workflow.",
    ),
    "NOD-RQA-KTL-CRV-SUB-ADA": _variant(
        "NOD-RQA-KTL-CRV-SUB-ADA",
        name="No Knowledge Graph",
        description="Full four-node workflow without the file-backed knowledge graph; query_knowledge uses an independent reference-reading agent over references directly.",
        node_prompts={
            "problem-contract": "rqa-problem-contract.md",
            "knowledge-to-tools": "rqa-knowledge-to-tools.md",
            "iterative-solving": "rqa-iterative.md",
        },
        node_purposes={
            "problem-contract": "依据用户需求、references 原文和数据 exploration 建立 problem contract 与 data spec；不构建或读取知识图谱。",
            "knowledge-to-tools": "用 references 原文和直接 reference QA 构建并校验 deterministic reference feature extractor，不依赖 knowledge graph。",
            "iterative-solving": "保留完整候选、subagent、case review 和迭代机制，但领域知识通过直接 reference QA 获取，不使用知识图谱。",
        },
    ),
    "NOD-RQA-KTL-SUB-ADA": _variant(
        "NOD-RQA-KTL-SUB-ADA",
        name="No Knowledge Graph + No Case Review",
        description="Direct-reference-QA workflow with case review, bad/good-case attribution, and case visualization removed.",
        node_prompts={
            "problem-contract": "rqa-problem-contract.md",
            "knowledge-to-tools": "rqa-knowledge-to-tools.md",
            "iterative-solving": "no-case-review-iterative.md",
            "final-summary": "no-case-review-final.md",
        },
        node_purposes={
            "iterative-solving": "在直接 reference QA 基础上保留候选和迭代，只依据聚合验证指标、执行状态和成本选择方案，不执行 case-level review 或可视化。"
        },
    ),
    "NOD-RQA-CRV-SUB-ADA": _variant(
        "NOD-RQA-CRV-SUB-ADA",
        name="No Knowledge Graph + No Knowledge Tools",
        description="Direct-reference-QA workflow without the knowledge-to-tools node or reference feature extractor.",
        node_prompts={
            "problem-contract": "rqa-problem-contract.md",
            "iterative-solving": "no-knowledge-tools-iterative.md",
        },
        node_purposes={
            "knowledge-to-tools": "本变体跳过 knowledge-to-tools 节点；不构建 reference feature extractor。",
            "iterative-solving": "保留直接 reference QA、候选、subagent、case review 和迭代机制，但不使用 reference feature extractor。",
        },
    ),
    "NOD-RQA-SUB-ADA": _variant(
        "NOD-RQA-SUB-ADA",
        name="No Knowledge Graph + No Case Review + No Knowledge Tools",
        description="Direct-reference-QA workflow without case review and without the knowledge-to-tools/reference-feature-extractor path.",
        node_prompts={
            "problem-contract": "rqa-problem-contract.md",
            "iterative-solving": "no-case-review-no-knowledge-tools-iterative.md",
            "final-summary": "no-case-review-final.md",
        },
        node_purposes={
            "knowledge-to-tools": "本变体跳过 knowledge-to-tools 节点；不构建 reference feature extractor。",
            "iterative-solving": "在去除 knowledge tools 的基础上同时去除 case review，只依据聚合验证指标、执行状态、成本和直接 reference QA 选择方案。",
        },
    ),
    DIRECT_FEATURE: _variant(
        DIRECT_FEATURE,
        name="Single-Agent Tool Use",
        description="One ordinary coding-agent session with data, code, and tool access; no node chain, knowledge query agent, knowledge graph, candidate subagents, structured case review, or iteration state.",
        main_prompt="direct-agent-main.md",
    ),
}


def canonical_variant_id(value: str) -> str:
    features = _parse_features(value)
    return _canonicalize_features(set(features))


def get_variant(value: str) -> AblationVariant:
    canonical_id = canonical_variant_id(value)
    try:
        return VARIANTS[canonical_id]
    except KeyError as exc:
        registered = ", ".join(VARIANTS)
        raise RuntimeError(
            f"Invalid TS_HARNESS_VARIANT={value!r}; {canonical_id} is syntactically valid but not a registered "
            f"ablation profile. Registered profiles: {registered}."
        ) from exc


def resolve_variant() -> AblationVariant:
    return get_variant(os.getenv("TS_HARNESS_VARIANT", DEFAULT_VARIANT_ID))


def variant_catalog_payload() -> dict[str, Any]:
    return {
        "default": DEFAULT_VARIANT_ID,
        "featureCodes": FEATURE_DESCRIPTIONS,
        "canonicalOrder": list(FEATURE_ORDER),
        "legacyAliases": dict(LEGACY_ALIASES),
        "registeredProfiles": [
            {
                "id": variant.id,
                "name": variant.name,
                "description": variant.description,
                "features": sorted(variant.features, key=_feature_sort_key),
                "legacyAliases": [alias for alias, target in LEGACY_ALIASES.items() if target == variant.id],
            }
            for variant in VARIANTS.values()
        ],
    }


def variant_help_text() -> str:
    profiles = "\n".join(
        f"  - {item['id']} ({', '.join(item['legacyAliases']) or 'no legacy alias'}): {item['name']}"
        for item in variant_catalog_payload()["registeredProfiles"]
    )
    feature_codes = "\n".join(f"  - {code}: {description}" for code, description in FEATURE_DESCRIPTIONS.items())
    aliases = ", ".join(f"{alias}->{target}" for alias, target in LEGACY_ALIASES.items())
    return "\n".join([
        "TS_HARNESS_VARIANT selects one startup-only ablation profile.",
        f"Default: {DEFAULT_VARIANT_ID}",
        "",
        "Feature codes:",
        feature_codes,
        "",
        "Registered canonical profiles:",
        profiles,
        "",
        "Legacy aliases are accepted for compatibility only:",
        f"  {aliases}",
        "",
        "Examples:",
        f"  TS_HARNESS_VARIANT={DEFAULT_VARIANT_ID} uv run ts-harness-server",
        "  TS_HARNESS_VARIANT=NOD-RQA-SUB-ADA uv run ts-harness-server",
        "  TS_HARNESS_VARIANT=RQA-NOD-SUB-ADA uv run ts-harness-server  # accepted; canonicalizes to NOD-RQA-SUB-ADA",
        "",
        "Rules:",
        "  - Order does not matter; the server records the canonical order.",
        "  - DIR cannot be combined with other codes.",
        "  - KGR and RQA are mutually exclusive.",
        "  - Non-DIR profiles must include NOD and exactly one of KGR or RQA.",
        "  - Syntactically valid but unregistered combinations fail fast.",
    ])
