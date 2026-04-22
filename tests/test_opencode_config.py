"""Coverage for the YAML → opencode.json generator (H6.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.lib.endpoints import load_endpoints
from orchestrator.lib.opencode_config import (
    OPENCODE_CONFIG_SCHEMA_URL,
    OPENCODE_OPENAI_COMPAT_NPM,
    build_agent_definitions,
    build_opencode_config,
    opencode_config_path,
    write_opencode_config,
)


def _two_endpoint_cfg():
    data = {
        "endpoints": [
            {
                "name": "local-gpu",
                "base_url": "http://127.0.0.1:8080",
                "model": "qwen3-coder:30b",
            },
            {
                "name": "openrouter",
                "base_url": "https://openrouter.ai/api",
                "model": "anthropic/claude-sonnet-4.5",
                "api_key_env": "OPENROUTER_API_KEY",
                "headers": {
                    "HTTP-Referer": "https://guildr.local",
                    "X-Title": "guildr",
                },
            },
        ],
        "routing": {
            "architect": [
                "openrouter",
                {"endpoint": "local-gpu", "model": "qwen3-coder:30b-review"},
            ],
            "coder": [{"endpoint": "local-gpu", "model": "qwen3-coder:30b"}],
        },
    }
    return load_endpoints(data, env={"OPENROUTER_API_KEY": "sk-test"})


def test_build_registers_every_declared_endpoint_as_provider() -> None:
    cfg = _two_endpoint_cfg()
    payload = build_opencode_config(cfg)
    assert payload["$schema"] == OPENCODE_CONFIG_SCHEMA_URL
    assert set(payload["provider"]) == {"local-gpu", "openrouter"}
    for provider in payload["provider"].values():
        assert provider["npm"] == OPENCODE_OPENAI_COMPAT_NPM


def test_base_url_is_suffixed_with_v1() -> None:
    cfg = _two_endpoint_cfg()
    payload = build_opencode_config(cfg)
    assert payload["provider"]["local-gpu"]["options"]["baseURL"] == (
        "http://127.0.0.1:8080/v1"
    )
    assert payload["provider"]["openrouter"]["options"]["baseURL"] == (
        "https://openrouter.ai/api/v1"
    )


def test_api_key_and_headers_propagate_to_provider_options() -> None:
    cfg = _two_endpoint_cfg()
    payload = build_opencode_config(cfg)
    openrouter = payload["provider"]["openrouter"]["options"]
    assert openrouter["apiKey"] == "sk-test"
    assert openrouter["headers"] == {
        "HTTP-Referer": "https://guildr.local",
        "X-Title": "guildr",
    }
    # Endpoints without api_key or headers don't carry those keys.
    local = payload["provider"]["local-gpu"]["options"]
    assert "apiKey" not in local
    assert "headers" not in local


def test_all_models_reachable_by_routing_are_registered() -> None:
    """Opencode must know about every model the engine might pass via --model.

    That is the endpoint default plus every route-level override that
    targets the endpoint — even overrides declared on a different role.
    """
    cfg = _two_endpoint_cfg()
    payload = build_opencode_config(cfg)
    # local-gpu default + the qwen3-coder:30b-review override from
    # architect's second route entry + the coder route's explicit
    # qwen3-coder:30b (identical to default → still one entry).
    assert set(payload["provider"]["local-gpu"]["models"]) == {
        "qwen3-coder:30b",
        "qwen3-coder:30b-review",
    }
    assert set(payload["provider"]["openrouter"]["models"]) == {
        "anthropic/claude-sonnet-4.5",
    }


def test_write_creates_parent_dirs_and_valid_json(tmp_path: Path) -> None:
    cfg = _two_endpoint_cfg()
    written = write_opencode_config(cfg, tmp_path)
    assert written == opencode_config_path(tmp_path)
    assert written.exists()
    # Parent directory hierarchy was created.
    assert written.parent == tmp_path / ".orchestrator" / "opencode"
    # File parses as JSON and round-trips to the same payload.
    on_disk = json.loads(written.read_text(encoding="utf-8"))
    assert on_disk == build_opencode_config(cfg)


def test_write_overwrites_existing_file(tmp_path: Path) -> None:
    """The JSON is a derivative — regenerating must overwrite cleanly."""
    cfg = _two_endpoint_cfg()
    first = write_opencode_config(cfg, tmp_path)
    first.write_text("stale\n", encoding="utf-8")
    write_opencode_config(cfg, tmp_path)
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert "provider" in payload  # stale content was replaced, not appended


def test_model_entry_name_includes_endpoint_label() -> None:
    """Cosmetic but useful for TUI disambiguation — same model id on two
    endpoints should render with distinct display names."""
    data = {
        "endpoints": [
            {"name": "fast", "base_url": "http://a", "model": "qwen:30b"},
            {"name": "slow", "base_url": "http://b", "model": "qwen:30b"},
        ],
    }
    cfg = load_endpoints(data)
    assert cfg is not None
    payload = build_opencode_config(cfg)
    assert payload["provider"]["fast"]["models"]["qwen:30b"]["name"] == (
        "qwen:30b @ fast"
    )
    assert payload["provider"]["slow"]["models"]["qwen:30b"]["name"] == (
        "qwen:30b @ slow"
    )


def test_narrator_agent_is_read_only() -> None:
    tools = build_agent_definitions()["narrator"]["tools"]
    assert tools["read"] is True
    assert tools["grep"] is True
    assert tools["bash"] is False
    assert tools["write"] is False
    assert tools["edit"] is False
    assert tools["webfetch"] is False
