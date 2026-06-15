from __future__ import annotations

from harnessing_ts.chain_summary import chain_summary_from_logs, normalize_chain_summary
from harnessing_ts.state.jsonl import append_jsonl


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
    assert summary["iterations"][0]["nextStep"] == "iterative-solving"
    assert summary["iterations"][0]["artifacts"][0]["path"] == "reports/iterations/iter-001-summary.md"
