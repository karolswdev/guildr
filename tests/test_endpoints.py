"""Coverage for the declarative endpoints/routing loader (H5.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.lib.endpoints import (
    EndpointsConfig,
    EndpointsConfigError,
    MEMPALACE_MCP_ALLOWED_ROLES,
    RouteEntry,
    load_endpoints,
    load_endpoints_from_yaml,
)


def _basic_endpoints() -> list[dict]:
    return [
        {"name": "local", "base_url": "http://127.0.0.1:8080", "model": "qwen-local"},
        {
            "name": "remote-sonnet",
            "base_url": "https://openrouter.ai/api",
            "model": "anthropic/claude-sonnet-4.5",
            "api_key_env": "MY_KEY",
            "headers": {"HTTP-Referer": "https://guildr.local"},
            "extra_body": {},
        },
    ]


def test_load_returns_none_when_neither_block_present() -> None:
    assert load_endpoints({}) is None
    assert load_endpoints({"llama_server_url": "http://x"}) is None


def test_load_parses_endpoints_and_routing() -> None:
    data = {
        "endpoints": _basic_endpoints(),
        "routing": {
            "architect": [
                "remote-sonnet",
                {"endpoint": "local", "model": "qwen-local-override"},
            ],
            "coder": ["local"],
        },
    }

    cfg = load_endpoints(data, env={"MY_KEY": "sk-real"})
    assert isinstance(cfg, EndpointsConfig)
    assert [e.name for e in cfg.endpoints] == ["local", "remote-sonnet"]
    assert cfg.by_name["remote-sonnet"].api_key == "sk-real"
    assert cfg.by_name["remote-sonnet"].headers == {"HTTP-Referer": "https://guildr.local"}
    assert cfg.by_name["remote-sonnet"].extra_body == {}

    architect = cfg.routing["architect"]
    assert architect[0] == RouteEntry(endpoint="remote-sonnet", model=None)
    assert architect[1] == RouteEntry(endpoint="local", model="qwen-local-override")
    assert cfg.routing["coder"] == [RouteEntry(endpoint="local")]
    assert cfg.memory_mcp.enabled is True
    assert cfg.memory_mcp.roles == ("coder", "tester", "reviewer", "narrator")


def test_missing_required_endpoint_field_raises() -> None:
    with pytest.raises(EndpointsConfigError, match="base_url"):
        load_endpoints({"endpoints": [{"name": "x", "model": "m"}]})
    with pytest.raises(EndpointsConfigError, match="model"):
        load_endpoints({"endpoints": [{"name": "x", "base_url": "http://x"}]})
    with pytest.raises(EndpointsConfigError, match="name"):
        load_endpoints({"endpoints": [{"base_url": "http://x", "model": "m"}]})


def test_unresolved_api_key_env_raises() -> None:
    data = {
        "endpoints": [
            {
                "name": "remote",
                "base_url": "https://x",
                "model": "m",
                "api_key_env": "MISSING_VAR",
            }
        ]
    }
    with pytest.raises(EndpointsConfigError, match="MISSING_VAR"):
        load_endpoints(data, env={})


def test_duplicate_endpoint_names_raise() -> None:
    data = {
        "endpoints": [
            {"name": "dup", "base_url": "http://a", "model": "m"},
            {"name": "dup", "base_url": "http://b", "model": "m"},
        ]
    }
    with pytest.raises(EndpointsConfigError, match="Duplicate"):
        load_endpoints(data)


def test_routing_references_unknown_endpoint_raises() -> None:
    data = {
        "endpoints": [{"name": "a", "base_url": "http://x", "model": "m"}],
        "routing": {"coder": ["b"]},
    }
    with pytest.raises(EndpointsConfigError, match="unknown endpoint 'b'"):
        load_endpoints(data)


def test_env_overrides_take_precedence_over_yaml() -> None:
    data = {
        "endpoints": [
            {"name": "remote-sonnet", "base_url": "https://from-yaml", "model": "yaml-model"},
        ],
    }
    env = {
        "ORCHESTRATOR_ENDPOINT_REMOTE_SONNET_BASE_URL": "https://from-env",
        "ORCHESTRATOR_ENDPOINT_REMOTE_SONNET_MODEL": "env-model",
        "ORCHESTRATOR_ENDPOINT_REMOTE_SONNET_API_KEY": "sk-env",
    }
    cfg = load_endpoints(data, env=env)
    assert cfg is not None
    spec = cfg.by_name["remote-sonnet"]
    assert spec.base_url == "https://from-env"
    assert spec.model == "env-model"
    assert spec.api_key == "sk-env"


def test_inline_api_key_is_accepted() -> None:
    data = {
        "endpoints": [
            {"name": "r", "base_url": "https://x", "model": "m", "api_key": "inline"},
        ]
    }
    cfg = load_endpoints(data, env={})
    assert cfg is not None
    assert cfg.by_name["r"].api_key == "inline"


def test_load_from_yaml_file_roundtrip(tmp_path: Path) -> None:
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(
        """\
endpoints:
  - name: local
    base_url: http://127.0.0.1:8080
    model: qwen-local
routing:
  coder:
    - local
    - endpoint: local
      model: qwen-alt
""",
        encoding="utf-8",
    )
    cfg = load_endpoints_from_yaml(yaml_path, env={})
    assert cfg is not None
    assert cfg.routing["coder"][1].model == "qwen-alt"


def test_memory_mcp_config_overrides_default_safe_roles() -> None:
    data = {
        "endpoints": [{"name": "local", "base_url": "http://x", "model": "m"}],
        "routing": {"coder": ["local"]},
        "memory_mcp": {
            "enabled": True,
            "roles": ["coder", "tester", "reviewer", "narrator"],
            "command": ["python", "-m", "mempalace.mcp_server"],
            "timeout_ms": 9000,
            "environment": {"MEMPALACE_PROFILE": "project"},
        },
    }

    cfg = load_endpoints(data, env={})

    assert cfg is not None
    assert cfg.memory_mcp.enabled is True
    assert cfg.memory_mcp.roles == ("coder", "tester", "reviewer", "narrator")
    assert set(cfg.memory_mcp.roles) <= set(MEMPALACE_MCP_ALLOWED_ROLES)
    assert cfg.memory_mcp.command == ("python", "-m", "mempalace.mcp_server")
    assert cfg.memory_mcp.timeout_ms == 9000
    assert cfg.memory_mcp.environment == {"MEMPALACE_PROFILE": "project"}


def test_memory_mcp_env_overrides_yaml() -> None:
    data = {
        "endpoints": [{"name": "local", "base_url": "http://x", "model": "m"}],
        "routing": {"coder": ["local"]},
        "memory_mcp": {"enabled": False},
    }

    cfg = load_endpoints(
        data,
        env={
            "GUILDR_MEMPALACE_MCP_ENABLED": "true",
            "GUILDR_MEMPALACE_MCP_ROLES": "coder,narrator",
            "GUILDR_MEMPALACE_MCP_COMMAND": "uvx --from mempalace python -m mempalace.mcp_server",
        },
    )

    assert cfg is not None
    assert cfg.memory_mcp.enabled is True
    assert cfg.memory_mcp.roles == ("coder", "narrator")
    assert cfg.memory_mcp.command == ("uvx", "--from", "mempalace", "python", "-m", "mempalace.mcp_server")


def test_memory_mcp_can_be_explicitly_disabled() -> None:
    data = {
        "endpoints": [{"name": "local", "base_url": "http://x", "model": "m"}],
        "routing": {"coder": ["local"]},
        "memory_mcp": {"enabled": False},
    }

    cfg = load_endpoints(data, env={})

    assert cfg is not None
    assert cfg.memory_mcp.enabled is False


def test_memory_mcp_rejects_zero_tool_roles() -> None:
    data = {
        "endpoints": [{"name": "local", "base_url": "http://x", "model": "m"}],
        "routing": {"architect": ["local"]},
        "memory_mcp": {"enabled": True, "roles": ["architect"]},
    }

    with pytest.raises(EndpointsConfigError, match="selected tool-using roles"):
        load_endpoints(data, env={})
