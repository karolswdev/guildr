"""Tests for the Deployer role on the opencode session runtime (H6.3d)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from orchestrator.lib.opencode import (
    OpencodeMessage,
    OpencodeResult,
    OpencodeTokens,
)
from orchestrator.lib.state import State
from orchestrator.roles.deployer import Deployer, DeployerError


# ---------------------------------------------------------------------------
# Fake SessionRunner
# ---------------------------------------------------------------------------


def _result(text: str, *, exit_code: int = 0) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="fake",
        model="fake",
        tokens=OpencodeTokens(total=1, input=1, output=0),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id="ses_test",
        exit_code=exit_code,
        directory=".",
        messages=[message] if text else [],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


@dataclass
class _FakeRunner:
    result: OpencodeResult | None = None
    exc: Exception | None = None
    prompts: list[str] = field(default_factory=list)

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def state(tmp_path):
    return State(tmp_path)


@pytest.fixture
def runner():
    return _FakeRunner()


@pytest.fixture
def deployer(runner, state):
    return Deployer(runner, state)


# ---------------------------------------------------------------------------
# _detect_deploy_configs / _detect_env_vars / _load_review (unchanged)
# ---------------------------------------------------------------------------


class TestDetectDeployConfigs:
    def test_detects_dockerfile(self, deployer, state):
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")
        assert "- Dockerfile" in deployer._detect_deploy_configs()

    def test_detects_multiple_configs(self, deployer, state):
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")
        (state.project_dir / "docker-compose.yml").write_text("version: '3'")
        result = deployer._detect_deploy_configs()
        assert "- Dockerfile" in result
        assert "- docker-compose.yml" in result

    def test_no_configs_returns_message(self, deployer, state):
        assert "No deployment configs" in deployer._detect_deploy_configs()

    def test_detects_fly_toml(self, deployer, state):
        (state.project_dir / "fly.toml").write_text("app = 'test'")
        assert "- fly.toml" in deployer._detect_deploy_configs()


class TestDetectEnvVars:
    def test_detects_os_environ(self, deployer, state):
        (state.project_dir / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        assert "SECRET_KEY" in deployer._detect_env_vars()

    def test_detects_os_getenv(self, deployer, state):
        (state.project_dir / "app.py").write_text("import os\nKEY = os.getenv('DATABASE_URL')")
        assert "DATABASE_URL" in deployer._detect_env_vars()

    def test_detects_known_patterns(self, deployer, state):
        (state.project_dir / "app.py").write_text("JWT_SECRET = 'placeholder'")
        assert "JWT_SECRET" in deployer._detect_env_vars()

    def test_no_env_vars_returns_default(self, deployer, state):
        (state.project_dir / "app.py").write_text("print('hi')")
        assert deployer._detect_env_vars() == ["No environment variables detected."]

    def test_skips_hidden_and_venv(self, deployer, state):
        for name in (".hidden", ".venv", "__pycache__"):
            d = state.project_dir / name
            d.mkdir()
            (d / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        assert "SECRET_KEY" not in deployer._detect_env_vars()

    def test_returns_sorted(self, deployer, state):
        (state.project_dir / "app.py").write_text(
            "import os\na = os.environ['ZZZ_VAR']\nb = os.environ['AAA_VAR']"
        )
        vars_ = deployer._detect_env_vars()
        assert vars_ == sorted(vars_)

    def test_ignores_private_vars(self, deployer, state):
        (state.project_dir / "app.py").write_text("import os\nKEY = os.environ['_PRIVATE_VAR']")
        assert "_PRIVATE_VAR" not in deployer._detect_env_vars()


class TestLoadReview:
    def test_loads_review(self, deployer, state):
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        assert "APPROVED" in deployer._load_review("REVIEW.md")

    def test_returns_default_when_missing(self, deployer):
        assert "No review available" in deployer._load_review("REVIEW.md")


# ---------------------------------------------------------------------------
# execute — the opencode-driven path
# ---------------------------------------------------------------------------


class TestExecute:
    def test_writes_deploy_md(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        runner.result = _result("# Deployment Plan\n\nTarget: Docker")
        path = deployer.execute("REVIEW.md")
        assert path == "DEPLOY.md"
        assert len(runner.prompts) == 1
        assert "Target: Docker" in state.read_file("DEPLOY.md")

    def test_prompt_includes_configs(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        (state.project_dir / "Dockerfile").write_text("FROM python:3.12")
        runner.result = _result("# plan")
        deployer.execute("REVIEW.md")
        assert "Dockerfile" in runner.prompts[0]

    def test_prompt_includes_env_vars(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review\n\nAPPROVED")
        (state.project_dir / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        runner.result = _result("# plan")
        deployer.execute("REVIEW.md")
        assert "SECRET_KEY" in runner.prompts[0]

    def test_runner_exception_is_wrapped(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review")
        runner.exc = RuntimeError("boom")
        with pytest.raises(DeployerError, match="opencode session failed"):
            deployer.execute("REVIEW.md")

    def test_non_zero_exit_raises(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review")
        runner.result = _result("partial", exit_code=3)
        with pytest.raises(DeployerError, match="rc=3"):
            deployer.execute("REVIEW.md")

    def test_empty_assistant_text_raises(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review")
        runner.result = _result("")
        with pytest.raises(DeployerError, match="no assistant text"):
            deployer.execute("REVIEW.md")

    def test_emits_audit_entries(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review")
        runner.result = _result("# plan")
        deployer.execute("REVIEW.md")
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        usage_path = state.project_dir / ".orchestrator" / "logs" / "usage.jsonl"
        assert raw_path.exists()
        assert usage_path.exists()
        assert "deployer" in raw_path.read_text(encoding="utf-8")

    def test_audit_fires_even_on_non_zero_exit(self, deployer, runner, state):
        state.write_file("REVIEW.md", "# Review")
        runner.result = _result("partial", exit_code=2)
        with pytest.raises(DeployerError):
            deployer.execute("REVIEW.md")
        raw_path = state.project_dir / ".orchestrator" / "logs" / "raw-io.jsonl"
        assert raw_path.exists()
        assert "deployer" in raw_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# get_required_env_vars
# ---------------------------------------------------------------------------


class TestGetRequiredEnvVars:
    def test_returns_env_vars(self, deployer, state):
        (state.project_dir / "app.py").write_text("import os\nKEY = os.environ['SECRET_KEY']")
        assert "SECRET_KEY" in deployer.get_required_env_vars()

    def test_returns_default_when_none(self, deployer, state):
        (state.project_dir / "app.py").write_text("print('hi')")
        assert deployer.get_required_env_vars() == ["No environment variables detected."]
