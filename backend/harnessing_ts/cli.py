from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from harnessing_ts.orchestrator import HarnessOrchestrator
from harnessing_ts.paths import default_workspace_path
from harnessing_ts.schema import NODE_TYPES
from harnessing_ts.settings.llm import build_sdk_invocation_config, mask_llm_config, mask_sdk_invocation_config, read_effective_llm_config
from harnessing_ts.training.lightning import write_training_template


def main() -> None:
    asyncio.run(_main())


async def _main() -> None:
    parser = argparse.ArgumentParser(prog="ts-harness")
    parser.add_argument("--workspace")
    parser.add_argument("--dry-run", action="store_true")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init")
    sub.add_parser("state")
    sub.add_parser("llm-config")

    send = sub.add_parser("send")
    send.add_argument("text", nargs="+")

    start = sub.add_parser("start-node")
    start.add_argument("node_type", choices=NODE_TYPES)
    start.add_argument("--rationale")
    start.add_argument("--input-summary")

    finish = sub.add_parser("finish-node")
    finish.add_argument("--summary", default="Finished by CLI.")
    finish.add_argument("--success", default="true")
    finish.add_argument("--goal-met")
    finish.add_argument("--next-node", choices=[*NODE_TYPES, "none"])
    finish.add_argument("--loop-decision", choices=["continue", "exit", "none"])
    finish.add_argument("--output-path")

    training = sub.add_parser("training-template")
    training.add_argument("--output", default="examples/training/agent_lightning_template.py")

    args = parser.parse_args()
    workspace = Path(args.workspace).expanduser().resolve() if args.workspace else default_workspace_path()
    control_mode = os.getenv("TS_HARNESS_CONTROL_MODE", "auto").strip().lower()
    if control_mode not in {"auto", "manual"}:
        control_mode = "auto"
    orchestrator = HarnessOrchestrator(workspace, dry_run=args.dry_run, locale="zh", mode=control_mode)
    command = args.command or "init"

    if command == "init":
        print_json(orchestrator.initialize())
        return
    if command == "state":
        print_json(orchestrator.get_state())
        return
    if command == "llm-config":
        cfg = read_effective_llm_config(workspace)
        print_json({"config": mask_llm_config(cfg), "sdk": mask_sdk_invocation_config(build_sdk_invocation_config(cfg))})
        return
    if command == "send":
        print_json(await orchestrator.send_main_user_message(" ".join(args.text)))
        await orchestrator.close()
        return
    if command == "start-node":
        print_json(await orchestrator.request_enter_node({
            "nodeType": args.node_type,
            "rationale": args.rationale or f"CLI start-node {args.node_type}",
            "inputSummary": args.input_summary,
        }))
        await orchestrator.close()
        return
    if command == "finish-node":
        print_json(await orchestrator.request_finish_node({
            "success": str(args.success).lower() != "false",
            "summary": args.summary,
            "goalMet": _optional_bool(args.goal_met),
            "nextNode": args.next_node,
            "loopDecision": args.loop_decision,
            "outputPaths": [args.output_path] if args.output_path else None,
        }))
        return
    if command == "training-template":
        path = write_training_template(workspace, Path(args.output))
        print_json({"path": str(path)})
        return
    raise SystemExit(f"Unknown command: {command}")


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "y"}


if __name__ == "__main__":
    main()
