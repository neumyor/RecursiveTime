from __future__ import annotations

from pathlib import Path

TEMPLATE = '''"""Agent Lightning training scaffold for HarnessingTS.

Install optional dependencies first:

    uv sync --extra training

This scaffold treats the harness output as an agent rollout and leaves reward
definition to the task owner. It is intentionally outside the normal web server
dependency path because training stacks can be heavy.
"""

from __future__ import annotations

from typing import TypedDict

import agentlightning as agl


class TimeSeriesHarnessTask(TypedDict):
    user_request: str
    expected_behavior: str


def grade_harness_output(final_answer: str, expected_behavior: str) -> float:
    """Replace with a task-specific grader.

    For ECG5000 abnormal sample classification this could score whether the
    generated tool-use protocol requires morphology checks, similarity evidence,
    uncertainty handling, and representative case review without leaking labels.
    """
    if not final_answer.strip():
        return 0.0
    return 1.0 if expected_behavior.lower() in final_answer.lower() else 0.2


class HarnessPromptAgent(agl.LitAgent):
    def training_rollout(self, task: TimeSeriesHarnessTask, rollout_id: str, resources: agl.NamedResources) -> float:
        prompt_template: agl.PromptTemplate = resources["main_prompt"]
        prompt = prompt_template.template.format(user_request=task["user_request"])
        # Wire this to a dry-run HarnessingTS invocation, a real Claude Code SDK run,
        # or a saved transcript replay depending on the training target.
        final_answer = prompt
        return grade_harness_output(final_answer, task["expected_behavior"])

    def validation_rollout(self, task: TimeSeriesHarnessTask, rollout_id: str, resources: agl.NamedResources) -> float:
        return self.training_rollout(task, rollout_id, resources)


def build_initial_prompt() -> agl.PromptTemplate:
    return agl.PromptTemplate(
        template="""You are a time-series tool-use harness agent.
User request: {user_request}
Design a tool-use protocol grounded in data evidence and domain knowledge.
Return the protocol and explicit uncertainty handling rules.""",
        engine="f-string",
    )
'''


def write_training_template(workspace: Path, output: Path) -> Path:
    path = output if output.is_absolute() else workspace / output
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path
