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
