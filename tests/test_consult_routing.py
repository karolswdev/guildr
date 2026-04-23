"""Tests for per-trigger consult routing (A-8.5a)."""

from __future__ import annotations

import os

import pytest

from orchestrator.lib.config import ConsultConfig
from orchestrator.lib.consult_routing import (
    DEFAULT_MODE_OVERRIDES,
    load_consult_config_from_env,
    resolve_policy,
)


def test_resolve_policy_uses_top_level_default() -> None:
    cfg = ConsultConfig(mode="deterministic", provider="primary", model="qwen")
    policy = resolve_policy("architect_plan_done", cfg)
    assert policy is not None
    assert policy.mode == "deterministic"
    assert policy.provider == "primary"
    assert policy.model == "qwen"


def test_resolve_policy_respects_overrides() -> None:
    cfg = ConsultConfig(
        mode="deterministic",
        mode_overrides={"reviewer_done": "model"},
        provider="primary",
        provider_overrides={"reviewer_done": "alien"},
        model_overrides={"reviewer_done": "qwen2.5-coder-32b"},
        max_tokens=1200,
        max_tokens_overrides={"reviewer_done": 600},
    )
    policy = resolve_policy("reviewer_done", cfg)
    assert policy is not None
    assert policy.mode == "model"
    assert policy.provider == "alien"
    assert policy.model == "qwen2.5-coder-32b"
    assert policy.max_tokens == 600


def test_resolve_policy_returns_none_for_disabled() -> None:
    cfg = ConsultConfig(disabled_triggers={"coder_done"})
    assert resolve_policy("coder_done", cfg) is None
    assert resolve_policy("architect_plan_done", cfg) is not None


def test_env_override_parses_json_mode_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GUILDR_CONSULT_MODE_OVERRIDES",
        '{"reviewer_done": "model", "coder_done": "deterministic"}',
    )
    cfg = load_consult_config_from_env(ConsultConfig())
    assert cfg.mode_overrides["reviewer_done"] == "model"
    assert cfg.mode_overrides["coder_done"] == "deterministic"


def test_env_override_ignores_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GUILDR_CONSULT_MODE_OVERRIDES", "not-json")
    cfg = load_consult_config_from_env(ConsultConfig())
    assert cfg.mode_overrides == {}


def test_env_override_disabled_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "GUILDR_CONSULT_DISABLED_TRIGGERS", "coder_done, tester_done"
    )
    cfg = load_consult_config_from_env(ConsultConfig())
    assert cfg.disabled_triggers == {"coder_done", "tester_done"}


def test_env_override_rejects_unknown_mode_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "GUILDR_CONSULT_MODE_OVERRIDES", '{"coder_done": "bogus"}'
    )
    cfg = load_consult_config_from_env(ConsultConfig())
    assert "coder_done" not in cfg.mode_overrides


def test_default_mode_overrides_covers_all_triggers() -> None:
    from orchestrator.lib.consult import TRIGGER_TAGS

    assert set(DEFAULT_MODE_OVERRIDES.keys()) == set(TRIGGER_TAGS.keys())
