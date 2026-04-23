"""Per-trigger policy resolver for founding-team consults (A-8.5a)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

from orchestrator.lib.config import ConsultConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedConsultPolicy:
    trigger_tag: str
    mode: str
    provider: str
    model: str
    max_tokens: int
    temperature: float
    timeout_s: float
    fallback_on_error: bool


def resolve_policy(
    trigger_tag: str, cfg: ConsultConfig
) -> ResolvedConsultPolicy | None:
    """Return the effective policy for a trigger, or None if disabled."""
    if trigger_tag in cfg.disabled_triggers:
        return None
    return ResolvedConsultPolicy(
        trigger_tag=trigger_tag,
        mode=cfg.mode_overrides.get(trigger_tag, cfg.mode),
        provider=cfg.provider_overrides.get(trigger_tag, cfg.provider),
        model=cfg.model_overrides.get(trigger_tag, cfg.model),
        max_tokens=cfg.max_tokens_overrides.get(trigger_tag, cfg.max_tokens),
        temperature=cfg.temperature,
        timeout_s=cfg.timeout_s,
        fallback_on_error=cfg.fallback_on_error,
    )


def load_consult_config_from_env(base: ConsultConfig | None = None) -> ConsultConfig:
    """Layer env overrides on top of a base ConsultConfig.

    Recognized env vars:
      - GUILDR_CONSULT_MODE ("deterministic" | "model")
      - GUILDR_CONSULT_PROVIDER
      - GUILDR_CONSULT_MODEL
      - GUILDR_CONSULT_MAX_TOKENS (int)
      - GUILDR_CONSULT_MODE_OVERRIDES  (JSON object {tag: mode})
      - GUILDR_CONSULT_PROVIDER_OVERRIDES (JSON object)
      - GUILDR_CONSULT_DISABLED_TRIGGERS (comma-separated tags)
    """
    cfg = base or ConsultConfig()
    mode = os.environ.get("GUILDR_CONSULT_MODE")
    if mode in ("deterministic", "model"):
        cfg.mode = mode
    provider = os.environ.get("GUILDR_CONSULT_PROVIDER")
    if provider:
        cfg.provider = provider
    model = os.environ.get("GUILDR_CONSULT_MODEL")
    if model:
        cfg.model = model
    max_tokens = os.environ.get("GUILDR_CONSULT_MAX_TOKENS")
    if max_tokens:
        try:
            cfg.max_tokens = int(max_tokens)
        except ValueError:
            logger.warning("GUILDR_CONSULT_MAX_TOKENS not an int: %r", max_tokens)

    cfg.mode_overrides = {
        **cfg.mode_overrides,
        **_load_json_map("GUILDR_CONSULT_MODE_OVERRIDES", allowed_values={"deterministic", "model"}),
    }
    cfg.provider_overrides = {
        **cfg.provider_overrides,
        **_load_json_map("GUILDR_CONSULT_PROVIDER_OVERRIDES"),
    }
    cfg.model_overrides = {
        **cfg.model_overrides,
        **_load_json_map("GUILDR_CONSULT_MODEL_OVERRIDES"),
    }

    disabled = os.environ.get("GUILDR_CONSULT_DISABLED_TRIGGERS", "")
    if disabled:
        cfg.disabled_triggers = set(cfg.disabled_triggers) | {
            tag.strip() for tag in disabled.split(",") if tag.strip()
        }
    return cfg


def _load_json_map(name: str, *, allowed_values: set[str] | None = None) -> dict[str, str]:
    raw = os.environ.get(name, "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("%s is not valid JSON; ignoring", name)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("%s did not parse as an object; ignoring", name)
        return {}
    out: dict[str, str] = {}
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        if allowed_values is not None and v not in allowed_values:
            continue
        out[k] = v
    return out


DEFAULT_MODE_OVERRIDES: dict[str, str] = {
    "architect_plan_done": "deterministic",
    "architect_refine_done": "deterministic",
    "micro_task_breakdown_done": "deterministic",
    "coder_done": "deterministic",
    "tester_done": "deterministic",
    "reviewer_done": "deterministic",
    "gate_rejected": "deterministic",
}
