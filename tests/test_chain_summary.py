from __future__ import annotations

import pytest

from harnessing_ts.chain_summary import (
    CHAIN_DRAFT_PATH,
    CHAIN_GENERATE_TOOLS,
    CHAIN_MAX_REPAIR_ATTEMPTS,
    CHAIN_REPAIR_TOOLS,
    chain_summary_from_logs,
    normalize_chain_summary,
    read_and_validate_chain_draft,
    validate_chain_summary,
)
from harnessing_ts.prompts.compose import (
    build_chain_summary_generate_prompt,
    build_chain_summary_repair_prompt,
    build_chain_summary_repair_system_prompt,
    build_chain_summary_system_prompt,
)
from harnessing_ts.state.jsonl import append_jsonl, write_json


def test_normalize_chain_summary_keeps_metric_series_and_samples() -> None:
    summary = normalize_chain_summary({
        "title": "Trajectory",
        "metricSeries": [
            {
                "name": "accuracy",
                "unit": "%",
                "direction": "higher",
                "values": [
                    {"iteration": "iter-1", "label": "I1", "value": "0.71"},
                    {"iteration": "iter-2", "label": "I2", "value": 0.82},
                ],
            }
        ],
        "iterations": [
            {
                "iterationId": "iter-1",
                "methods": [{"name": "Candidate 1", "hypothesis": "use morphology"}],
                "methodResults": [{
                    "methodName": "Candidate 1",
                    "metric": "Macro AUC",
                    "value": "0.91",
                    "evidencePath": "reports/iterations/iter-1-candidate-review.md",
                    "interpretation": "best candidate in this iteration",
                }],
                "sampleInspirations": [
                    {
                        "sampleId": "42",
                        "visualizationPath": "runs/iterations/iter-1/case-42.png",
                        "interpretation": "borderline morphology",
                        "nextIterationImpact": "add morphology feature",
                    }
                ],
            }
        ],
    })

    assert summary["metricSeries"][0]["values"][0]["value"] == 0.71
    assert summary["iterations"][0]["methodResults"][0]["methodName"] == "Candidate 1"
    assert summary["iterations"][0]["methodResults"][0]["metric"] == "Macro AUC"
    assert summary["iterations"][0]["sampleInspirations"][0]["visualizationPath"].endswith("case-42.png")


def test_normalize_chain_summary_keeps_structured_next_decision() -> None:
    summary = normalize_chain_summary({
        "iterations": [{
            "iterationId": "iter-1",
            "nextDecision": {
                "decision": "下一轮增加P波专用分支。",
                "iterationEvidence": "当前模型持续遗漏心房扩大样本。",
                "domainKnowledge": [{
                    "knowledge": "左心房扩大常表现为P波增宽。",
                    "sourcePath": "knowledge_base/ecg.md",
                    "guidance": "保留高时间分辨率以检测P波时限。",
                }],
                "actions": [{
                    "action": "增加P波分支",
                    "expectedEffect": "提升HYP召回率",
                    "validation": "比较HYP AUC与LAE子集召回率",
                }],
            },
        }],
    })

    decision = summary["iterations"][0]["nextDecision"]
    assert decision["domainKnowledge"][0]["sourcePath"] == "knowledge_base/ecg.md"
    assert decision["actions"][0]["validation"] == "比较HYP AUC与LAE子集召回率"
    assert "summary" not in summary["iterations"][0]


def test_chain_summary_placeholder_reads_timeline_iterations(tmp_path) -> None:
    (tmp_path / "logs").mkdir()
    append_jsonl(tmp_path / "logs" / "timeline.jsonl", {
        "type": "node_finished",
        "timestamp": "2026-01-01T00:00:00Z",
        "nodeSessionId": "node-1",
        "nodeType": "iterative-solving",
        "message": "First iteration completed.",
        "payload": {
            "loopDecision": "continue",
            "nextNode": "iterative-solving",
            "outputPaths": ["reports/iterations/iter-001-summary.md"],
        },
    })

    summary = chain_summary_from_logs(tmp_path)

    assert summary["iterations"][0]["iterationId"] == "node-1"
    assert summary["iterations"][0]["nextDecision"]["decision"] == "iterative-solving"
    assert summary["iterations"][0]["artifacts"][0]["path"] == "reports/iterations/iter-001-summary.md"


def test_validate_chain_summary_rejects_shallow_knowledge_decision(tmp_path) -> None:
    knowledge = tmp_path / "knowledge_base"
    knowledge.mkdir()
    (knowledge / "domain.md").write_text("domain knowledge", encoding="utf-8")
    summary = normalize_chain_summary({
        "iterations": [
            {
                "iterationId": "iter-1",
                "nextDecision": {
                    "decision": "测试新方法",
                    "iterationEvidence": "本轮指标退化",
                    "domainKnowledge": [],
                    "actions": [{"action": "训练", "expectedEffect": "提升AUC", "validation": "对比AUC"}],
                },
            },
            {"iterationId": "iter-2"},
        ],
    })

    with pytest.raises(RuntimeError, match="at least two sourced domain-knowledge links"):
        validate_chain_summary(summary, tmp_path)


def test_validate_chain_summary_rejects_english_user_facing_content(tmp_path) -> None:
    summary = normalize_chain_summary({
        "title": "English chain summary",
        "overview": "Only English content.",
        "iterations": [],
    })

    with pytest.raises(RuntimeError, match="must contain Simplified Chinese"):
        validate_chain_summary(summary, tmp_path)


def test_chain_builder_separates_generate_and_repair_tools() -> None:
    assert "Write" in CHAIN_GENERATE_TOOLS
    assert "Edit" not in CHAIN_GENERATE_TOOLS
    assert "Edit" in CHAIN_REPAIR_TOOLS
    assert "Write" not in CHAIN_REPAIR_TOOLS
    assert CHAIN_MAX_REPAIR_ATTEMPTS == 6


def test_backend_reads_and_validates_draft_file(tmp_path) -> None:
    draft = tmp_path / CHAIN_DRAFT_PATH
    write_json(draft, {
        "title": "思维链总结",
        "overview": "当前决策链概览。",
        "iterations": [],
        "uncertainty": [],
    })

    summary = read_and_validate_chain_draft(draft, tmp_path)

    assert summary["title"] == "思维链总结"


def test_chain_summary_prompt_fragments_are_assembled() -> None:
    system_prompt = build_chain_summary_system_prompt()
    generate_prompt = build_chain_summary_generate_prompt(
        manifest_json='{"reports": ["iter-1.md"]}',
        draft_path=CHAIN_DRAFT_PATH,
    )
    repair_system_prompt = build_chain_summary_repair_system_prompt()
    repair_prompt = build_chain_summary_repair_prompt(
        validation_error="iterations[0].nextDecision 缺少领域知识映射",
        attempt=2,
        max_attempts=CHAIN_MAX_REPAIR_ATTEMPTS,
        draft_path=CHAIN_DRAFT_PATH,
    )

    assert "Chain Summary Builder" in system_prompt
    assert '"nextDecision"' in system_prompt
    assert '"reports": ["iter-1.md"]' in generate_prompt
    assert CHAIN_DRAFT_PATH in generate_prompt
    assert "Chain Summary Repair Agent" in repair_system_prompt
    assert "第 2/6 次局部修复" in repair_prompt
    assert "缺少领域知识映射" in repair_prompt
    assert "{manifest_json}" not in generate_prompt
    assert "{validation_error}" not in repair_prompt
