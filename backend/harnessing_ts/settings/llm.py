from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from harnessing_ts.paths import project_root

LlmProtocol = Literal["anthropic", "openai-compat"]
LlmAuthMode = Literal["sdk-default", "manual"]
ANTHROPIC_MESSAGES_SUFFIX = re.compile(r"/v1/messages/?$", re.I)


@dataclass(frozen=True)
class LlmConfig:
    authMode: LlmAuthMode = "sdk-default"
    model: str = ""
    apiKey: str | None = None
    baseUrl: str | None = None
    protocol: LlmProtocol | None = None
    contextWindow: Literal["200k", "1m"] | None = None


@dataclass(frozen=True)
class SdkInvocationConfig:
    model: str | None = None
    env: dict[str, str] | None = None
    extra_args: dict[str, Any] | None = None


def read_effective_llm_config(workspace_path: Path) -> LlmConfig:
    file_config = _read_llm_config_file(workspace_path)
    env_config = _read_llm_env_config()
    return LlmConfig(
        authMode=env_config.authMode if env_config.authMode != "sdk-default" else file_config.authMode,
        model=env_config.model or file_config.model,
        apiKey=env_config.apiKey or file_config.apiKey,
        baseUrl=env_config.baseUrl or file_config.baseUrl,
        protocol=env_config.protocol or file_config.protocol,
        contextWindow=env_config.contextWindow or file_config.contextWindow,
    )


def build_sdk_invocation_config(cfg: LlmConfig) -> SdkInvocationConfig:
    model = cfg.model.strip() or None
    extra_args: dict[str, Any] = {}
    if cfg.contextWindow == "1m":
        # The Claude Code SDK transport prepends its own "--" to every
        # extra_args key (see claude_code_sdk/_internal/transport/subprocess_cli.py
        # line ~157: `cmd.extend([f"--{flag}", str(value)])`). Putting the
        # leading "--" on the key here would produce "----betas" and the
        # CLI rejects the unknown option on startup, hanging the harness
        # until the SDK's 60s "initialize" control-request timeout fires.
        extra_args["betas"] = "context-1m-2025-08-07"
    if cfg.authMode != "manual" or not cfg.apiKey:
        return SdkInvocationConfig(model=model, extra_args=extra_args or None)

    protocol = infer_manual_protocol(cfg)
    sdk_base_url = normalize_sdk_base_url(cfg.baseUrl, protocol)
    env = dict(os.environ)
    if protocol == "anthropic":
        env["ANTHROPIC_AUTH_TOKEN"] = cfg.apiKey.strip()
        env["ANTHROPIC_API_KEY"] = cfg.apiKey.strip()
        if model:
            env["ANTHROPIC_MODEL"] = model
            env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model
            env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model
            env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model
            env["CLAUDE_CODE_SUBAGENT_MODEL"] = model
        if sdk_base_url:
            env["ANTHROPIC_BASE_URL"] = sdk_base_url
    else:
        env["ANTHROPIC_API_KEY"] = cfg.apiKey.strip()
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        if sdk_base_url:
            env["ANTHROPIC_BASE_URL"] = sdk_base_url
    return SdkInvocationConfig(model=model, env=env, extra_args=extra_args or None)


def infer_manual_protocol(cfg: LlmConfig) -> LlmProtocol:
    if cfg.protocol:
        return cfg.protocol
    endpoint = (cfg.baseUrl or "").strip()
    return "anthropic" if ANTHROPIC_MESSAGES_SUFFIX.search(endpoint) or re.search(r"/apps/anthropic/?$", endpoint, re.I) else "openai-compat"


def normalize_sdk_base_url(base_url: str | None, protocol: LlmProtocol) -> str | None:
    endpoint = (base_url or "").strip()
    if not endpoint:
        return None
    if protocol != "anthropic":
        return endpoint
    return ANTHROPIC_MESSAGES_SUFFIX.sub("", endpoint) or endpoint


def mask_sdk_invocation_config(cfg: SdkInvocationConfig) -> dict[str, Any]:
    env = cfg.env or {}
    out: dict[str, Any] = {}
    if cfg.model:
        out["model"] = cfg.model
    if cfg.extra_args:
        out["extraArgs"] = cfg.extra_args
    if env:
        out["env"] = {
            "ANTHROPIC_BASE_URL": env.get("ANTHROPIC_BASE_URL"),
            "ANTHROPIC_MODEL": env.get("ANTHROPIC_MODEL"),
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL"),
            "ANTHROPIC_DEFAULT_SONNET_MODEL": env.get("ANTHROPIC_DEFAULT_SONNET_MODEL"),
            "ANTHROPIC_DEFAULT_OPUS_MODEL": env.get("ANTHROPIC_DEFAULT_OPUS_MODEL"),
            "CLAUDE_CODE_SUBAGENT_MODEL": env.get("CLAUDE_CODE_SUBAGENT_MODEL"),
            "ANTHROPIC_AUTH_TOKEN": _mask_secret(env.get("ANTHROPIC_AUTH_TOKEN")),
            "ANTHROPIC_API_KEY": _mask_secret(env.get("ANTHROPIC_API_KEY")),
        }
    return out


def mask_llm_config(cfg: LlmConfig) -> dict[str, Any]:
    return {
        "authMode": cfg.authMode,
        "model": cfg.model,
        **({"apiKey": _mask_secret(cfg.apiKey)} if cfg.apiKey else {}),
        **({"baseUrl": cfg.baseUrl} if cfg.baseUrl else {}),
        **({"protocol": cfg.protocol} if cfg.protocol else {}),
        **({"contextWindow": cfg.contextWindow} if cfg.contextWindow else {}),
    }


def _read_llm_config_file(workspace_path: Path) -> LlmConfig:
    for path in (
        workspace_path / "config.llm.json",
        Path.cwd() / "config.llm.json",
        project_root() / "config.llm.json",
    ):
        if path.exists():
            return _sanitize_config(json.loads(path.read_text(encoding="utf-8")))
    return LlmConfig()


def _read_llm_env_config() -> LlmConfig:
    return _sanitize_config({
        "authMode": os.getenv("TS_HARNESS_LLM_AUTH_MODE"),
        "protocol": os.getenv("TS_HARNESS_LLM_PROTOCOL"),
        "model": os.getenv("TS_HARNESS_LLM_MODEL"),
        "apiKey": os.getenv("TS_HARNESS_LLM_API_KEY"),
        "baseUrl": os.getenv("TS_HARNESS_LLM_BASE_URL"),
        "contextWindow": os.getenv("TS_HARNESS_LLM_CONTEXT_WINDOW"),
    })


def _sanitize_config(raw: dict[str, Any]) -> LlmConfig:
    auth = raw.get("authMode") if raw.get("authMode") in {"manual", "sdk-default"} else "sdk-default"
    protocol = raw.get("protocol") if raw.get("protocol") in {"anthropic", "openai-compat"} else None
    context = raw.get("contextWindow") if raw.get("contextWindow") in {"200k", "1m"} else None
    return LlmConfig(
        authMode=auth,
        model=raw.get("model") if isinstance(raw.get("model"), str) else "",
        apiKey=raw.get("apiKey") if isinstance(raw.get("apiKey"), str) else None,
        baseUrl=raw.get("baseUrl") if isinstance(raw.get("baseUrl"), str) else None,
        protocol=protocol,
        contextWindow=context,
    )


def _mask_secret(secret: str | None) -> str | None:
    if not secret:
        return None
    return "****" if len(secret) <= 8 else f"****{secret[-4:]}"
