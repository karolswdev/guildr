"""Tests for orchestrator.lib.config."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from orchestrator.lib.config import Config


@pytest.fixture
def yaml_config(tmp_path: Path) -> Path:
    """Write a minimal valid YAML config and return its path."""
    data = {
        "llama_server_url": "http://127.0.0.1:8080",
        "project_dir": str(tmp_path / "project"),
        "max_retries": 5,
        "architect_max_passes": 4,
        "architect_pass_threshold": 5,
        "quiz_min_turns": 4,
        "quiz_max_turns": 8,
        "require_human_approval": False,
        "expose_public": True,
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    """Write a YAML config with only required fields."""
    data = {
        "llama_server_url": "http://127.0.0.1:8080",
        "project_dir": str(tmp_path / "project"),
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


class TestFromYaml:
    """Test Config.from_yaml()."""

    def test_loads_full_config(self, yaml_config: Path):
        cfg = Config.from_yaml(yaml_config)
        assert cfg.llama_server_url == "http://127.0.0.1:8080"
        assert cfg.max_retries == 5
        assert cfg.architect_max_passes == 4
        assert cfg.architect_pass_threshold == 5
        assert cfg.quiz_min_turns == 4
        assert cfg.quiz_max_turns == 8
        assert cfg.require_human_approval is False
        assert cfg.expose_public is True

    def test_loads_minimal_config(self, minimal_yaml: Path):
        cfg = Config.from_yaml(minimal_yaml)
        assert cfg.llama_server_url == "http://127.0.0.1:8080"
        # Defaults for optional fields
        assert cfg.max_retries == 3
        assert cfg.max_total_iterations == 20
        assert cfg.architect_max_passes == 3
        assert cfg.architect_pass_threshold == 4
        assert cfg.quiz_min_turns == 3
        assert cfg.quiz_max_turns == 10
        assert cfg.require_human_approval is True
        assert cfg.expose_public is False

    def test_defaults_expose_public_false(self, minimal_yaml: Path):
        cfg = Config.from_yaml(minimal_yaml)
        assert cfg.expose_public is False

    def test_missing_required_field(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.dump({"project_dir": str(tmp_path / "p")}), encoding="utf-8")
        with pytest.raises(ValueError, match="Missing required config fields"):
            Config.from_yaml(path)

    def test_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            Config.from_yaml(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("{invalid: yaml: [}", encoding="utf-8")
        with pytest.raises(Exception):  # yaml.YAMLError
            Config.from_yaml(path)

    def test_yaml_with_hyphenated_keys(self, tmp_path: Path):
        """YAML keys with hyphens should be mapped to snake_case."""
        data = {
            "llama-server-url": "http://127.0.0.1:8080",
            "project-dir": str(tmp_path / "project"),
            "max-retries": 7,
        }
        path = tmp_path / "hyphen.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        cfg = Config.from_yaml(path)
        assert cfg.llama_server_url == "http://127.0.0.1:8080"
        assert cfg.max_retries == 7

    def test_round_trip(self, tmp_path: Path):
        """Write YAML → load → compare struct."""
        original = Config(
            llama_server_url="http://127.0.0.1:8080",
            project_dir=tmp_path / "project",
            max_retries=5,
            max_total_iterations=25,
            architect_max_passes=4,
            architect_pass_threshold=5,
            quiz_min_turns=4,
            quiz_max_turns=8,
            require_human_approval=False,
            expose_public=True,
        )
        data = {}
        for f in original.__dataclass_fields__.values():
            v = getattr(original, f.name)
            if isinstance(v, Path):
                v = str(v)
            data[f.name] = v
        path = tmp_path / "roundtrip.yaml"
        path.write_text(yaml.dump(data), encoding="utf-8")
        loaded = Config.from_yaml(path)
        for f in original.__dataclass_fields__.values():
            assert getattr(loaded, f.name) == getattr(original, f.name)


class TestFromEnv:
    """Test Config.from_env()."""

    def test_minimal_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("LLAMA_SERVER_URL", "http://10.0.0.1:8080")
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path / "proj"))
        cfg = Config.from_env()
        assert cfg.llama_server_url == "http://10.0.0.1:8080"
        assert cfg.project_dir == tmp_path / "proj"
        assert cfg.expose_public is False

    def test_missing_url(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("LLAMA_SERVER_URL", raising=False)
        monkeypatch.delenv("LLAMA_URL", raising=False)
        monkeypatch.delenv("LLAMA_PRIMARY_URL", raising=False)
        with pytest.raises(ValueError, match="required"):
            Config.from_env()

    def test_env_overrides_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("LLAMA_SERVER_URL", "http://10.0.0.1:8080")
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path / "proj"))
        monkeypatch.setenv("ORCHESTRATOR_MAX_RETRIES", "10")
        monkeypatch.setenv("ORCHESTRATOR_MAX_ITERATIONS", "50")
        monkeypatch.setenv("REQUIRE_HUMAN_APPROVAL", "false")
        monkeypatch.setenv("EXPOSE_PUBLIC", "1")
        cfg = Config.from_env()
        assert cfg.max_retries == 10
        assert cfg.max_total_iterations == 50
        assert cfg.require_human_approval is False
        assert cfg.expose_public is True

    def test_legacy_url_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("LLAMA_URL", "http://10.0.0.2:8080")
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path / "proj"))
        cfg = Config.from_env()
        assert cfg.llama_server_url == "http://10.0.0.2:8080"

    def test_primary_url_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("LLAMA_PRIMARY_URL", "http://10.0.0.3:8080")
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path / "proj"))
        cfg = Config.from_env()
        assert cfg.llama_server_url == "http://10.0.0.3:8080"

    def test_primary_takes_precedence(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("LLAMA_SERVER_URL", "http://10.0.0.1:8080")
        monkeypatch.setenv("LLAMA_URL", "http://10.0.0.2:8080")
        monkeypatch.setenv("PROJECT_DIR", str(tmp_path / "proj"))
        cfg = Config.from_env()
        assert cfg.llama_server_url == "http://10.0.0.1:8080"
