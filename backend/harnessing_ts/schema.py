from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from harnessing_ts.config.markdown import node_documents

NodeType = str
ControlMode = Literal["manual", "auto"]
CONTROL_MODES: tuple[str, ...] = ("manual", "auto")


@dataclass(frozen=True)
class NodeSpec:
    type: NodeType
    phase: str
    purpose: str
    requires: tuple[str, ...]
    produces: tuple[str, ...]
    next: NodeType | None = None


def _load_node_specs() -> tuple[NodeSpec, ...]:
    specs: list[NodeSpec] = []
    for item in node_documents():
        specs.append(NodeSpec(
            type=item["type"],
            phase=item["phase"],
            purpose=item["purpose"],
            requires=tuple(item["requires"]),
            produces=tuple(item["produces"]),
            next=item.get("next"),
        ))
    return tuple(specs)


NODE_SPECS: tuple[NodeSpec, ...] = _load_node_specs()
NODE_TYPES: tuple[NodeType, ...] = tuple(spec.type for spec in NODE_SPECS)


class WorkspaceState(TypedDict):
    workspaceId: str
    workspacePath: str
    createdAt: str
    updatedAt: str
    mode: ControlMode
    controlMode: ControlMode
    pendingControl: "ControlRequest | None"
    activeNode: NodeType | None
    activeNodeSessionId: str | None
    completedNodes: list[NodeType]
    contractConfirmed: bool
    finalSummaryConfirmed: bool
    runtimeSettings: "RuntimeSettings"


class RuntimeSettings(TypedDict):
    iterativeCandidateCount: int
    knowledgeGraphExtractionDepth: int


class NodeSession(TypedDict, total=False):
    id: str
    nodeType: NodeType
    status: Literal["created", "running", "paused", "waiting_approval", "completed", "failed", "exited"]
    startedAt: str
    completedAt: str
    sdkSessionId: str
    rationale: str
    inputSummary: str
    summary: str
    success: bool
    goalMet: bool | None
    nextNode: NodeType | None
    loopDecision: Literal["continue", "exit", "none"] | None
    outputPaths: list[str]


class ControlRequest(TypedDict, total=False):
    id: str
    kind: Literal["enter_node", "finish_node"]
    status: Literal["pending"]
    createdAt: str
    nodeType: NodeType
    nodeSessionId: str
    args: dict[str, Any]
    message: str


class TimelineEvent(TypedDict, total=False):
    type: str
    timestamp: str
    nodeSessionId: str
    nodeType: NodeType
    message: str
    payload: Any


class Part(TypedDict, total=False):
    id: str
    timestamp: str
    role: Literal["user", "assistant", "system", "tool"]
    type: Literal["text", "tool_use", "tool_result", "result", "raw"]
    text: str
    name: str
    input: Any
    raw: Any


class RunRecord(TypedDict, total=False):
    runId: str
    nodeSessionId: str
    nodeType: NodeType
    status: Literal["running", "completed", "failed"]
    startedAt: str
    finishedAt: str
    artifactPaths: list[str]
    summary: str
    metrics: dict[str, Any]


def get_node_spec(node_type: NodeType) -> NodeSpec:
    for spec in NODE_SPECS:
        if spec.type == node_type:
            return spec
    raise ValueError(f"Unknown node type: {node_type}")


def get_next_node(node_type: NodeType) -> NodeType | None:
    return get_node_spec(node_type).next
