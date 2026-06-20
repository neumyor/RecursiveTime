from __future__ import annotations

from pathlib import Path

from harnessing_ts.config.markdown import node_document


REPO_ROOT = Path(__file__).resolve().parents[1]
TEXT_ROOTS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "AGENT.md",
    REPO_ROOT / "docs",
    REPO_ROOT / "backend" / "harnessing_ts" / "config",
]

FORBIDDEN_RUNTIME_RESIDUES = [
    "after cleanup",
    "re-enter the workspace",
    "restart the harness runner",
    "next `node_entered",
    "should be written to `logs/main.jsonl`",
    "should be written to logs/main.jsonl",
]


def _iter_text_files() -> list[Path]:
    files: list[Path] = []
    for root in TEXT_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".md", ".txt", ".yaml", ".yml"}
        )
    return sorted(files)


def test_docs_and_prompts_do_not_contain_runtime_residue() -> None:
    offenders: list[str] = []
    for path in _iter_text_files():
        text = path.read_text(encoding="utf-8").lower()
        for phrase in FORBIDDEN_RUNTIME_RESIDUES:
            if phrase in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {phrase}")

    assert offenders == []


def test_common_node_rules_do_not_forbid_task_when_node_allows_it() -> None:
    common_rules = (
        REPO_ROOT
        / "backend"
        / "harnessing_ts"
        / "config"
        / "prompts"
        / "node"
        / "execution-rules.md"
    ).read_text(encoding="utf-8")

    assert "不要用 Task 子代理" not in common_rules
    assert "只有当本 node 规范明确允许或要求 `Task` 时" in common_rules


def test_common_node_rules_allow_only_native_and_injected_harness_tools() -> None:
    common_rules = (
        REPO_ROOT
        / "backend"
        / "harnessing_ts"
        / "config"
        / "prompts"
        / "node"
        / "execution-rules.md"
    ).read_text(encoding="utf-8")

    assert "只能使用本 node 的 native tools，以及系统明确注入的 Harness MCP 工具" in common_rules


def test_node_specs_match_mandatory_output_contracts() -> None:
    problem_outputs = node_document("problem-contract")["produces"]
    iterative_outputs = node_document("iterative-solving")["produces"]

    assert "knowledge_base/domain-brief.md" not in problem_outputs
    assert problem_outputs == ["user/problem-contract.md", "user/data-spec.md"]
    assert "reports/iterations/<iteration-id>-candidate-review.md" in iterative_outputs


def test_final_summary_prompt_does_not_request_impossible_failure_reroute() -> None:
    guidance = node_document("final-summary")["guidance"]

    assert "routing inconsistency" not in guidance
    assert "要求回到 `iterative-solving`" not in guidance


def test_chain_summary_prompts_are_markdown_backed() -> None:
    chain_summary_source = (
        REPO_ROOT / "backend" / "harnessing_ts" / "chain_summary.py"
    ).read_text(encoding="utf-8")
    prompt_root = (
        REPO_ROOT / "backend" / "harnessing_ts" / "config" / "prompts" / "chain-summary"
    )

    assert "CHAIN_SYSTEM_PROMPT" not in chain_summary_source
    assert "CHAIN_REPAIR_SYSTEM_PROMPT" not in chain_summary_source
    assert "请生成 HarnessingTS 当前 workspace 的思维链总结" not in chain_summary_source
    assert {
        "system.md",
        "schema.md",
        "generate.md",
        "repair-system.md",
        "repair.md",
    } <= {path.name for path in prompt_root.glob("*.md")}
