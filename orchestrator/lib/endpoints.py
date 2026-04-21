"""Declarative endpoint + routing config (H5.2).

Replaces the single-``llama_server_url`` assumption with a heterogeneous
pool of OpenAI-compatible endpoints. Operators declare endpoints by
free-form name (``local-gpu``, ``openrouter-sonnet``, ``ollama-mac``,
...) and a per-role routing table that prefers one endpoint over another
and can override the endpoint's default model per role.

Wire shape (``config.yaml``):

    endpoints:
      - name: local-gpu
        base_url: http://127.0.0.1:8080
        model: qwen3-coder:30b
      - name: openrouter
        base_url: https://openrouter.ai/api
        model: anthropic/claude-sonnet-4.5
        api_key_env: OPENROUTER_API_KEY
        headers:
          HTTP-Referer: https://guildr.local
          X-Title: guildr
        extra_body: {}                # omit the Qwen thinking hint

    routing:
      architect:
        - openrouter                  # short form: use endpoint default model
        - endpoint: local-gpu         # long form: explicit model override
          model: qwen3-coder:30b
      coder:
        - local-gpu
      reviewer:
        - openrouter

Env overrides (applied after YAML, never silent about mismatches):

- ``ORCHESTRATOR_ENDPOINT_<NAME>_BASE_URL`` — override base_url
- ``ORCHESTRATOR_ENDPOINT_<NAME>_MODEL`` — override endpoint default model
- ``ORCHESTRATOR_ENDPOINT_<NAME>_API_KEY`` — inline API key (rare; prefer
  ``api_key_env`` indirection so the secret stays out of the shell history)

``<NAME>`` is upper-cased with non-alphanumerics → underscore, so
``openrouter-sonnet`` becomes ``ORCHESTRATOR_ENDPOINT_OPENROUTER_SONNET_*``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class EndpointSpec:
    """One OpenAI-compatible chat endpoint the pool can route to."""

    name: str
    base_url: str
    model: str
    api_key: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    extra_body: Any = None  # None = use LLMClient's default (Qwen hint); {} = omit; {...} = override


@dataclass
class RouteEntry:
    """One preference in a role's routing list: an endpoint + optional model override."""

    endpoint: str
    model: str | None = None


class EndpointsConfigError(ValueError):
    """Raised when the endpoints/routing config is structurally invalid."""


def _env_key(endpoint_name: str) -> str:
    """Normalize an endpoint name into an env var name component."""
    safe = re.sub(r"[^A-Za-z0-9]+", "_", endpoint_name).strip("_")
    return safe.upper()


def _resolve_endpoint(
    raw: Any,
    *,
    env: dict[str, str],
) -> EndpointSpec:
    if not isinstance(raw, dict):
        raise EndpointsConfigError(
            f"Each endpoint must be a mapping, got {type(raw).__name__}"
        )
    name = raw.get("name")
    if not name or not isinstance(name, str):
        raise EndpointsConfigError(
            f"Endpoint missing required 'name' (string): {raw!r}"
        )
    base_url = raw.get("base_url")
    model = raw.get("model")
    if not base_url or not isinstance(base_url, str):
        raise EndpointsConfigError(
            f"Endpoint '{name}' missing required 'base_url' (string)"
        )
    if not model or not isinstance(model, str):
        raise EndpointsConfigError(
            f"Endpoint '{name}' missing required 'model' (string)"
        )

    api_key: str | None = None
    if "api_key_env" in raw:
        env_var = raw["api_key_env"]
        if not isinstance(env_var, str) or not env_var:
            raise EndpointsConfigError(
                f"Endpoint '{name}' has non-string 'api_key_env'"
            )
        resolved = env.get(env_var)
        if resolved is None:
            raise EndpointsConfigError(
                f"Endpoint '{name}' references api_key_env='{env_var}' "
                f"but that variable is not set"
            )
        api_key = resolved
    elif "api_key" in raw:
        # Inline for ops convenience; config.yaml is expected to be gitignored.
        inline = raw["api_key"]
        if not isinstance(inline, str):
            raise EndpointsConfigError(
                f"Endpoint '{name}' has non-string 'api_key'"
            )
        api_key = inline

    headers = raw.get("headers") or {}
    if not isinstance(headers, dict):
        raise EndpointsConfigError(
            f"Endpoint '{name}' has non-mapping 'headers'"
        )
    headers = {str(k): str(v) for k, v in headers.items()}

    extra_body = raw.get("extra_body", None)

    env_prefix = f"ORCHESTRATOR_ENDPOINT_{_env_key(name)}"
    base_url = env.get(f"{env_prefix}_BASE_URL", base_url)
    model = env.get(f"{env_prefix}_MODEL", model)
    api_key_override = env.get(f"{env_prefix}_API_KEY")
    if api_key_override:
        api_key = api_key_override

    return EndpointSpec(
        name=name,
        base_url=base_url,
        model=model,
        api_key=api_key,
        headers=headers,
        extra_body=extra_body,
    )


def _resolve_route_entry(raw: Any, *, role: str, known: set[str]) -> RouteEntry:
    if isinstance(raw, str):
        endpoint = raw
        model: str | None = None
    elif isinstance(raw, dict):
        endpoint = raw.get("endpoint")
        model = raw.get("model")
        if not endpoint or not isinstance(endpoint, str):
            raise EndpointsConfigError(
                f"Routing for role '{role}' has entry missing 'endpoint': {raw!r}"
            )
        if model is not None and not isinstance(model, str):
            raise EndpointsConfigError(
                f"Routing for role '{role}' has non-string 'model' override: {raw!r}"
            )
    else:
        raise EndpointsConfigError(
            f"Routing for role '{role}' entries must be strings or mappings, "
            f"got {type(raw).__name__}"
        )
    if endpoint not in known:
        raise EndpointsConfigError(
            f"Routing for role '{role}' references unknown endpoint '{endpoint}'. "
            f"Known endpoints: {sorted(known)}"
        )
    return RouteEntry(endpoint=endpoint, model=model)


@dataclass
class EndpointsConfig:
    """Parsed + env-overridden endpoints + routing block."""

    endpoints: list[EndpointSpec]
    routing: dict[str, list[RouteEntry]]

    @property
    def by_name(self) -> dict[str, EndpointSpec]:
        return {e.name: e for e in self.endpoints}


def load_endpoints(
    data: dict[str, Any] | None,
    *,
    env: dict[str, str] | None = None,
) -> EndpointsConfig | None:
    """Parse the ``endpoints`` + ``routing`` blocks from a config mapping.

    Returns ``None`` when neither block is present — callers fall back to
    the legacy single-``llama_server_url`` path. Raises
    ``EndpointsConfigError`` on structural problems so misconfiguration is
    loud, not silent.
    """
    if not data:
        return None
    ep_raw = data.get("endpoints")
    rt_raw = data.get("routing")
    if ep_raw is None and rt_raw is None:
        return None
    if ep_raw is None or not isinstance(ep_raw, list) or not ep_raw:
        raise EndpointsConfigError(
            "'endpoints' must be a non-empty list when declared"
        )
    active_env = env if env is not None else dict(os.environ)

    endpoints = [_resolve_endpoint(e, env=active_env) for e in ep_raw]
    names = {e.name for e in endpoints}
    if len(names) != len(endpoints):
        dupes = [e.name for e in endpoints if sum(1 for x in endpoints if x.name == e.name) > 1]
        raise EndpointsConfigError(
            f"Duplicate endpoint names: {sorted(set(dupes))}"
        )

    routing: dict[str, list[RouteEntry]] = {}
    if rt_raw is not None:
        if not isinstance(rt_raw, dict):
            raise EndpointsConfigError("'routing' must be a mapping of role → list")
        for role, raw_entries in rt_raw.items():
            if not isinstance(raw_entries, list) or not raw_entries:
                raise EndpointsConfigError(
                    f"Routing for role '{role}' must be a non-empty list"
                )
            routing[str(role)] = [
                _resolve_route_entry(e, role=str(role), known=names) for e in raw_entries
            ]
    else:
        # No explicit routing — every role prefers every endpoint, in declared
        # order. Keeps the single-endpoint zero-config case painless.
        default = [RouteEntry(endpoint=e.name) for e in endpoints]
        routing = {}
        # Leave routing empty; pool.chat will surface NoHealthyEndpoint with
        # a clear 'no_routing_configured' reason unless the runner fills it.
        # Callers that want "any role → any endpoint" should declare it.
        # Keep behavior explicit: unrecognized role → NoHealthyEndpoint.
        # (Operators who forgot the routing block get a loud failure instead
        # of an implicit preference order that might surprise them.)
        del default  # noqa: F841

    return EndpointsConfig(endpoints=endpoints, routing=routing)


def load_endpoints_from_yaml(
    path: Path,
    *,
    env: dict[str, str] | None = None,
) -> EndpointsConfig | None:
    """Load an endpoints/routing block from a YAML file."""
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        return None
    return load_endpoints(data, env=env)


def build_pool(cfg: EndpointsConfig) -> Any:
    """Materialize an ``UpstreamPool`` from a parsed ``EndpointsConfig``.

    One ``LLMClient`` per endpoint (the client carries the endpoint's
    default model; per-role model overrides are applied by the pool at
    call time). Import of ``UpstreamPool`` is lazy to keep
    ``endpoints.py`` import-cheap for the config-only tests.
    """
    from orchestrator.lib.llm import LLMClient
    from orchestrator.lib.pool import Endpoint, UpstreamPool

    endpoints = []
    for spec in cfg.endpoints:
        client_kwargs: dict[str, Any] = {
            "model": spec.model,
        }
        if spec.api_key is not None:
            client_kwargs["api_key"] = spec.api_key
        if spec.headers:
            client_kwargs["default_headers"] = spec.headers
        if spec.extra_body is not None:
            client_kwargs["extra_body"] = spec.extra_body
        client = LLMClient(base_url=spec.base_url, **client_kwargs)
        endpoints.append(Endpoint(label=spec.name, client=client))
    return UpstreamPool(endpoints=endpoints, routing=dict(cfg.routing))
