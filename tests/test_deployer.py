"""Tests for Deployer role."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.llm import LLMClient, LLMResponse
from orchestrator.lib.state import State
from orchestrator.roles.deployer import (
    Deployer,
    DeployerError,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path):
    """Create a State instance backed by a temp directory."""
    return State(tmp_path)


@pytest.fixture
def llm_mock():
    """Create a mock LLMClient."""
    return MagicMock(spec=LLMClient)


@pytest.fixture
def deployer(llm_mock, state):
    """Create a Deployer instance."""
    return Deployer(llm_mock, state)


# ---------------------------------------------------------------------------
# Tests: _detect_deploy_configs
# ---------------------------------------------------------------------------


class TestDetectDeployConfigs:
    """Test deployment config detection."""

    def test_detects_dockerfile(self, deployer, state):
        """Dockerfile is detected."""
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")
        result = deployer._detect_deploy_configs()
        assert "- Dockerfile" in result

    def test_detects_docker_compose(self, deployer, state):
        """docker-compose.yml is detected."""
        (state.project_dir / "docker-compose.yml").write_text("version: '3'")
        result = deployer._detect_deploy_configs()
        assert "- docker-compose.yml" in result

    def test_detects_multiple_configs(self, deployer, state):
        """Multiple configs are detected."""
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")
        (state.project_dir / "docker-compose.yml").write_text("version: '3'")
        result = deployer._detect_deploy_configs()
        assert "- Dockerfile" in result
        assert "- docker-compose.yml" in result

    def test_no_configs_returns_message(self, deployer, state):
        """No configs returns a message."""
        result = deployer._detect_deploy_configs()
        assert "No deployment configs" in result

    def test_detects_fly_toml(self, deployer, state):
        """fly.toml is detected."""
        (state.project_dir / "fly.toml").write_text("app = 'test'")
        result = deployer._detect_deploy_configs()
        assert "- fly.toml" in result

    def test_detects_render_yaml(self, deployer, state):
        """render.yaml is detected."""
        (state.project_dir / "render.yaml").write_text("services: []")
        result = deployer._detect_deploy_configs()
        assert "- render.yaml" in result

    def test_detects_package_json(self, deployer, state):
        """package.json is detected."""
        (state.project_dir / "package.json").write_text('{"name": "test"}')
        result = deployer._detect_deploy_configs()
        assert "- package.json" in result


# ---------------------------------------------------------------------------
# Tests: _detect_env_vars
# ---------------------------------------------------------------------------


class TestDetectEnvVars:
    """Test environment variable detection from source code."""

    def test_detects_os_environ(self, deployer, state):
        """os.environ['VAR'] is detected."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.environ['SECRET_KEY']")
        vars = deployer._detect_env_vars()
        assert "SECRET_KEY" in vars

    def test_detects_os_getenv(self, deployer, state):
        """os.getenv('VAR') is detected."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.getenv('DATABASE_URL')")
        vars = deployer._detect_env_vars()
        assert "DATABASE_URL" in vars

    def test_detects_os_environ_get(self, deployer, state):
        """os.environ.get('VAR') is detected."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.environ.get('API_KEY')")
        vars = deployer._detect_env_vars()
        assert "API_KEY" in vars

    def test_detects_known_patterns(self, deployer, state):
        """Known patterns like JWT_SECRET are detected."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("JWT_SECRET = 'placeholder'")
        vars = deployer._detect_env_vars()
        assert "JWT_SECRET" in vars

    def test_no_env_vars_returns_default(self, deployer, state):
        """No env vars returns default message."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("print('hello')")
        vars = deployer._detect_env_vars()
        assert vars == ["No environment variables detected."]

    def test_skips_hidden_dirs(self, deployer, state):
        """Hidden directories are skipped."""
        hidden_dir = state.project_dir / ".hidden"
        hidden_dir.mkdir()
        (hidden_dir / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        vars = deployer._detect_env_vars()
        assert "SECRET_KEY" not in vars

    def test_skips_venv(self, deployer, state):
        """.venv directory is skipped."""
        venv_dir = state.project_dir / ".venv"
        venv_dir.mkdir()
        (venv_dir / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        vars = deployer._detect_env_vars()
        assert "SECRET_KEY" not in vars

    def test_skips_pycache(self, deployer, state):
        """__pycache__ directory is skipped."""
        pycache = state.project_dir / "__pycache__"
        pycache.mkdir()
        (pycache / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        vars = deployer._detect_env_vars()
        assert "SECRET_KEY" not in vars

    def test_returns_sorted(self, deployer, state):
        """Detected env vars are sorted."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\n"
                          "a = os.environ['ZZZ_VAR']\n"
                          "b = os.environ['AAA_VAR']")
        vars = deployer._detect_env_vars()
        assert vars == sorted(vars)

    def test_ignores_private_vars(self, deployer, state):
        """Private vars (starting with _) are ignored."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.environ['_PRIVATE_VAR']")
        vars = deployer._detect_env_vars()
        assert "_PRIVATE_VAR" not in vars


# ---------------------------------------------------------------------------
# Tests: _load_review
# ---------------------------------------------------------------------------


class TestLoadReview:
    """Test review loading."""

    def test_loads_review(self, deployer, state):
        """REVIEW.md is loaded."""
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        result = deployer._load_review("REVIEW.md")
        assert "APPROVED" in result

    def test_returns_default_when_missing(self, deployer, state):
        """Missing REVIEW.md returns default."""
        result = deployer._load_review("REVIEW.md")
        assert "No review available" in result


# ---------------------------------------------------------------------------
# Tests: execute
# ---------------------------------------------------------------------------


class TestExecute:
    """Test end-to-end execution."""

    def test_writes_deploy_md(self, deployer, llm_mock, state):
        """execute writes DEPLOY.md."""
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")

        llm_mock.chat.return_value = LLMResponse(
            content="# Deployment Plan\n\nTarget: Docker",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        result_path = deployer.execute("REVIEW.md")

        assert result_path == "DEPLOY.md"
        assert llm_mock.chat.call_count == 1

        deploy = state.read_file("DEPLOY.md")
        assert "Target: Docker" in deploy

    def test_includes_configs_in_prompt(self, deployer, llm_mock, state):
        """execute includes detected configs in prompt."""
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")

        llm_mock.chat.return_value = LLMResponse(
            content="# Deployment Plan\n\nTarget: Docker",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        deployer.execute("REVIEW.md")

        messages = llm_mock.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "Dockerfile" in user_content

    def test_includes_env_vars_in_prompt(self, deployer, llm_mock, state):
        """execute includes detected env vars in prompt."""
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.environ['SECRET_KEY']")

        llm_mock.chat.return_value = LLMResponse(
            content="# Deployment Plan\n\nTarget: Docker",
            reasoning="",
            prompt_tokens=100,
            completion_tokens=200,
            reasoning_tokens=0,
            finish_reason="stop",
        )

        deployer.execute("REVIEW.md")

        messages = llm_mock.chat.call_args[0][0]
        user_content = messages[1]["content"]
        assert "SECRET_KEY" in user_content

    def test_handles_llm_failure(self, deployer, llm_mock, state):
        """execute raises DeployerError on LLM failure."""
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")

        llm_mock.chat.side_effect = Exception("Connection refused")

        with pytest.raises(DeployerError, match="LLM call failed"):
            deployer.execute("REVIEW.md")


# ---------------------------------------------------------------------------
# Tests: get_required_env_vars
# ---------------------------------------------------------------------------


class TestGetRequiredEnvVars:
    """Test get_required_env_vars convenience method."""

    def test_returns_env_vars(self, deployer, state):
        """Returns detected env vars."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("import os\nKEY = os.environ['SECRET_KEY']")
        vars = deployer.get_required_env_vars()
        assert "SECRET_KEY" in vars

    def test_returns_empty_list_when_none(self, deployer, state):
        """Returns empty list when no env vars detected."""
        py_file = state.project_dir / "app.py"
        py_file.write_text("print('hello')")
        vars = deployer.get_required_env_vars()
        assert vars == ["No environment variables detected."]
