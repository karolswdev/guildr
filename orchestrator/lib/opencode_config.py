"""Generate a per-project ``opencode.json`` from an ``EndpointsConfig`` (H6.1).

H6 makes opencode the agent runtime for every SDLC role. Opencode reads
its providers + models from a JSON config; operators already declare
theirs via the H5.2 ``endpoints:`` block in ``config.yaml``. This
module bridges the two: one source of truth (our YAML), two consumers
(the orchestrator's engine + opencode).

We never mutate the user's ``~/.config/opencode/opencode.json`` — that
is their personal session tool. We generate a *per-project* overlay
under ``<project_dir>/.orchestrator/opencode/opencode.json`` and point
opencode at it via ``--dir`` or ``OPENCODE_CONFIG`` at spawn time.

Every distinct ``(endpoint, model)`` pair reachable from either the
endpoint default or a route-level override is registered, so the engine
can pass ``--model <endpoint>/<modelID>`` for any declared route.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.lib.endpoints import EndpointsConfig

OPENCODE_CONFIG_SCHEMA_URL = "https://opencode.ai/config.json"
OPENCODE_OPENAI_COMPAT_NPM = "@ai-sdk/openai-compatible"


def _models_per_endpoint(cfg: EndpointsConfig) -> dict[str, set[str]]:
    """Collect every model id each endpoint must register.

    An endpoint's default model is always in the set. Route-level
    overrides (``RouteEntry.model``) add to it because opencode needs
    every model id the engine might pass via ``--model`` to be declared
    up front.
    """
    per_endpoint: dict[str, set[str]] = {ep.name: {ep.model} for ep in cfg.endpoints}
    for entries in cfg.routing.values():
        for entry in entries:
            if entry.model:
                per_endpoint[entry.endpoint].add(entry.model)
    return per_endpoint


def build_opencode_config(cfg: EndpointsConfig) -> dict[str, Any]:
    """Return the opencode.json mapping for the given endpoints config.

    Shape matches ``~/.config/opencode/opencode.json`` as documented in
    ``docs/research/opencode-runtime.md``. We emit one provider per
    declared endpoint, wired through ``@ai-sdk/openai-compatible`` (the
    same adapter the operator's global config uses), with ``baseURL``
    suffixed ``/v1`` to match the OpenAI spec. Every distinct model is
    registered on the provider so ``--model <endpoint>/<modelID>``
    resolves.
    """
    models_by_endpoint = _models_per_endpoint(cfg)
    providers: dict[str, Any] = {}
    for ep in cfg.endpoints:
        options: dict[str, Any] = {"baseURL": f"{ep.base_url.rstrip('/')}/v1"}
        if ep.api_key is not None:
            options["apiKey"] = ep.api_key
        if ep.headers:
            options["headers"] = dict(ep.headers)
        providers[ep.name] = {
            "npm": OPENCODE_OPENAI_COMPAT_NPM,
            "name": ep.name,
            "options": options,
            "models": {
                model_id: {"name": f"{model_id} @ {ep.name}"}
                for model_id in sorted(models_by_endpoint[ep.name])
            },
        }
    return {
        "$schema": OPENCODE_CONFIG_SCHEMA_URL,
        "provider": providers,
        "agent": build_agent_definitions(),
    }


# ---------------------------------------------------------------------------
# Agent definitions (H6.3e)
# ---------------------------------------------------------------------------

# Tool surface opencode exposes today (from ``opencode agent create --help``):
# bash, read, write, edit, glob, grep, webfetch, task, todowrite.
_ALL_TOOLS = ("bash", "read", "write", "edit", "glob", "grep", "webfetch", "task", "todowrite")


def _tools(**overrides: bool) -> dict[str, bool]:
    """Start every tool disabled; flip the ones named in overrides."""
    base = {tool: False for tool in _ALL_TOOLS}
    base.update(overrides)
    return base


def build_agent_definitions() -> dict[str, Any]:
    """Per-role opencode agents with explicit tool allowlists (H6.3e).

    The architect and judge produce a text or JSON completion with no
    tool calls — so every tool is disabled. Agent-driven roles keep the
    minimal surface they actually need; nothing declared here grants
    wider access than the H6.3a–d behaviour they replaced.
    """
    return {
        "architect": {
            "mode": "primary",
            "description": "Produces sprint-plan.md from qwendea.md. Text output only.",
            "tools": _tools(),
        },
        "judge": {
            "mode": "primary",
            "description": "Scores an architect sprint plan against the rubric. JSON output only.",
            "tools": _tools(),
        },
        "coder": {
            "mode": "primary",
            "description": "Implements one sprint-plan task per session; reads + writes project files.",
            "tools": _tools(read=True, write=True, edit=True, glob=True, grep=True),
        },
        "tester": {
            "mode": "primary",
            "description": "Runs each task's Evidence Required commands and emits TEST_REPORT.md.",
            "tools": _tools(bash=True, read=True, glob=True, grep=True),
        },
        "reviewer": {
            "mode": "primary",
            "description": "Reads the diff + test report, emits a verdict. Read-only.",
            "tools": _tools(read=True, glob=True, grep=True),
        },
        "narrator": {
            "mode": "primary",
            "description": "Synthesizes sourced narrative digests from bounded event packets. Read-only.",
            "tools": _tools(read=True, grep=True),
        },
        "deployer": {
            "mode": "primary",
            "description": "Produces DEPLOY.md from detected deploy configs + env vars. Read-only.",
            "tools": _tools(read=True, glob=True, grep=True),
        },
    }


def opencode_config_path(project_dir: Path) -> Path:
    """Canonical per-project opencode.json path."""
    return project_dir / ".orchestrator" / "opencode" / "opencode.json"


def write_opencode_config(cfg: EndpointsConfig, project_dir: Path) -> Path:
    """Write the generated opencode.json under ``project_dir`` and return its path.

    Creates parent directories if needed. File is overwritten on each
    call — the YAML is the source of truth, the JSON is a derivative.
    """
    path = opencode_config_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_opencode_config(cfg)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
