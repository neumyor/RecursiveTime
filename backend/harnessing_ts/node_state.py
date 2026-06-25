from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from harnessing_ts.reference_feature_extractor import KNOWLEDGE_TO_TOOLS_REQUIRED_OUTPUT_PATHS
from harnessing_ts.schema import NODE_SPECS, NodeSession, NodeType, WorkspaceState, get_next_node
from harnessing_ts.variants import AblationVariant, get_variant


NODE_SPECS_BY_TYPE = {spec.type: spec for spec in NODE_SPECS}


class NodeStateMachine:
    def __init__(self, workspace_path: Path, variant: AblationVariant | None = None) -> None:
        self.workspace_path = workspace_path
        self.variant = variant or get_variant("V0")

    def is_pipeline_complete(self, state: WorkspaceState | None) -> bool:
        if not state:
            return False
        return (
            "final-summary" in state.get("completedNodes", [])
            and not state.get("activeNode")
            and not state.get("activeNodeSessionId")
        )

    def next_node_after_completion(self, latest: NodeSession) -> NodeType | None:
        if latest["nodeType"] == "iterative-solving":
            if latest.get("loopDecision") == "continue":
                return "iterative-solving"
            if latest.get("loopDecision") == "exit":
                return "final-summary"
            if latest.get("nextNodeSpecified") and latest.get("nextNode") is None:
                return None
            if latest.get("nextNode"):
                return latest.get("nextNode")
            if latest.get("goalMet") is True:
                return get_next_node(latest["nodeType"])
            return None
        if latest.get("nextNodeSpecified") and latest.get("nextNode") is None:
            return None
        if latest.get("nextNode"):
            return latest.get("nextNode")
        next_node = get_next_node(latest["nodeType"])
        if next_node == "knowledge-to-tools" and not self.variant.knowledge_to_tools:
            return "iterative-solving"
        return next_node

    def normalize_next_node(self, value: Any) -> NodeType | None:
        if value is None:
            return None
        node = str(value).strip()
        if not node or node == "none":
            return None
        if node not in NODE_SPECS_BY_TYPE:
            raise RuntimeError(f"Invalid nextNode from MCP finish_node: {node}")
        return node

    def normalize_loop_decision(self, value: Any) -> str | None:
        if value is None:
            return None
        decision = str(value).strip().lower()
        if not decision or decision == "none":
            return None
        if decision not in {"continue", "exit"}:
            raise RuntimeError(f"Invalid loopDecision from MCP finish_node: {decision}")
        return decision

    def validate_finish_control(
        self,
        node_type: NodeType,
        success: bool,
        next_node: NodeType | None,
        loop_decision: str | None,
        output_paths: list[str] | None = None,
        goal_met: bool | None = None,
        next_node_specified: bool = False,
    ) -> None:
        if node_type == "knowledge-to-tools":
            if success:
                self.validate_knowledge_to_tools_output_paths(output_paths or [])
            return
        if node_type != "iterative-solving":
            return
        if success and not loop_decision:
            raise RuntimeError("iterative-solving finish_node requires explicit loopDecision.")
        if success and next_node_specified and next_node is None:
            raise RuntimeError(
                "iterative-solving cannot explicitly set nextNode=none; "
                "use nextNode=iterative-solving with loopDecision=continue or "
                "nextNode=final-summary with loopDecision=exit."
            )
        if loop_decision == "continue" and next_node not in {None, "iterative-solving"}:
            raise RuntimeError("iterative-solving loopDecision=continue requires nextNode=iterative-solving.")
        if loop_decision == "exit" and next_node not in {None, "final-summary"}:
            raise RuntimeError("iterative-solving loopDecision=exit requires nextNode=final-summary.")
        route_decision = self.iterative_route_decision(next_node, loop_decision)
        if success and self.variant.max_iterations == 1 and route_decision != "exit":
            raise RuntimeError(
                f"{self.variant.id} permits exactly one iterative-solving round; "
                "finish with loopDecision=exit and nextNode=final-summary."
            )
        if success and route_decision == "continue" and goal_met is True:
            raise RuntimeError("iterative-solving cannot set goalMet=true while loopDecision=continue.")
        if success:
            self.validate_iterative_output_paths(output_paths or [])
        recommend_exit = self.read_iteration_state_recommend_exit()
        if recommend_exit is False and route_decision == "exit":
            raise RuntimeError(
                "iterative-solving finish_node requested final-summary, but user/iteration-state.md "
                "has recommend_exit: false. Use loopDecision=continue with nextNode=iterative-solving, "
                "or update iteration-state.md only if the contract stop criteria are actually met."
            )
        if recommend_exit is True and route_decision == "continue":
            raise RuntimeError(
                "iterative-solving finish_node requested another iteration, but user/iteration-state.md "
                "has recommend_exit: true. Use loopDecision=exit with nextNode=final-summary, "
                "or update iteration-state.md if the work should continue."
            )

    def validate_iterative_output_paths(self, output_paths: list[str]) -> None:
        normalized = [_workspace_relative_path(path, self.workspace_path) for path in output_paths]
        requirements = {
            "candidate review": r"^reports/iterations/.+-candidate-review\.md$",
            "iteration summary": r"^reports/iterations/.+-summary\.md$",
            "iteration state": r"^user/iteration-state\.md$",
        }
        if self.variant.case_review:
            requirements["case review"] = r"^reports/iterations/.+-case-review\.md$"
        missing = [
            label
            for label, pattern in requirements.items()
            if not any(re.match(pattern, path) for path in normalized)
        ]
        if missing:
            raise RuntimeError(
                "iterative-solving finish_node is missing required outputPaths: "
                + ", ".join(missing)
                + ". Complete the full node artifacts before calling finish_node."
            )

    def validate_knowledge_to_tools_output_paths(self, output_paths: list[str]) -> None:
        normalized = {_workspace_relative_path(path, self.workspace_path) for path in output_paths}
        required = set(KNOWLEDGE_TO_TOOLS_REQUIRED_OUTPUT_PATHS)
        missing = sorted(required - normalized)
        if missing:
            raise RuntimeError(
                "knowledge-to-tools finish_node is missing required outputPaths: "
                + ", ".join(missing)
                + ". Complete the full reference feature extractor contract before calling finish_node."
            )

    def iterative_route_decision(self, next_node: NodeType | None, loop_decision: str | None) -> str | None:
        if loop_decision in {"continue", "exit"}:
            return loop_decision
        if next_node == "iterative-solving":
            return "continue"
        if next_node == "final-summary":
            return "exit"
        return None

    def read_iteration_state_recommend_exit(self) -> bool | None:
        path = self.workspace_path / "user" / "iteration-state.md"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return None
        for line in text.splitlines()[:80]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("```"):
                continue
            if not stripped.startswith("recommend_exit"):
                continue
            _, _, raw = stripped.partition(":")
            value = raw.strip().strip("\"'").lower()
            if value == "true":
                return True
            if value == "false":
                return False
            return None
        return None


def _workspace_relative_path(path: str, workspace_path: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            return candidate.resolve().relative_to(workspace_path.resolve()).as_posix()
        except ValueError:
            return candidate.as_posix().lstrip("/")
    return candidate.as_posix().lstrip("./")
