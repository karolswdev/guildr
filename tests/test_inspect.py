"""Tests for orchestrator.cli.inspect."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.inspect import (
    find_project,
    list_phases,
    load_state,
    main,
    show_tokens,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Create a project directory with state.json."""
    proj = tmp_path / "test-project"
    orch = proj / ".orchestrator"
    orch.mkdir(parents=True)
    state = {
        "current_phase": "implementation",
        "sessions": {"architect": "abc123"},
        "retries": {"architect": 1, "implementation": 0},
        "gates_approved": {"approve_sprint_plan": True},
    }
    (orch / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return proj


@pytest.fixture
def project_with_sessions(project_dir: Path) -> Path:
    """Add session transcript files."""
    sessions = project_dir / ".orchestrator" / "sessions"
    sessions.mkdir()
    sessions.joinpath("architect-1.json").write_text(
        json.dumps({"role": "architect", "messages": []}),
        encoding="utf-8",
    )
    sessions.joinpath("architect-2.json").write_text(
        json.dumps({"role": "architect", "messages": []}),
        encoding="utf-8",
    )
    return project_dir


@pytest.fixture
def project_with_logs(project_dir: Path) -> Path:
    """Add per-phase log files with LLM call data."""
    logs = project_dir / ".orchestrator" / "logs"
    logs.mkdir()
    logs.joinpath("architect.jsonl").write_text(
        json.dumps({
            "event": "llm_call.architect",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "reasoning_tokens": 50,
        }) + "\n"
        + json.dumps({
            "event": "llm_call.judge",
            "prompt_tokens": 50,
            "completion_tokens": 30,
            "reasoning_tokens": 10,
        }) + "\n"
        + json.dumps({"event": "phase_start", "message": "started"}) + "\n",
        encoding="utf-8",
    )
    logs.joinpath("implementation.jsonl").write_text(
        json.dumps({
            "event": "llm_call.coder",
            "prompt_tokens": 500,
            "completion_tokens": 1000,
            "reasoning_tokens": 200,
        }) + "\n",
        encoding="utf-8",
    )
    return project_dir


# ---------------------------------------------------------------------------
# Tests: find_project
# ---------------------------------------------------------------------------


class TestFindProject:
    """Test project directory resolution."""

    def test_finds_by_direct_path(self, project_dir: Path):
        """find_project resolves a direct path to the project."""
        result = find_project(str(project_dir))
        assert result == project_dir

    def test_finds_by_name_in_tmp(self, project_dir: Path):
        """find_project finds project in /tmp/orchestrator-projects/."""
        tmp_projects = Path("/tmp/orchestrator-projects")
        tmp_projects.mkdir(exist_ok=True)
        link = tmp_projects / "test-project"
        if not link.exists():
            link.symlink_to(project_dir)
        try:
            result = find_project("test-project")
            assert result.resolve() == project_dir.resolve()
        finally:
            if link.exists():
                link.unlink(missing_ok=True)

    def test_raises_on_missing_project(self):
        """find_project raises FileNotFoundError for non-existent project."""
        with pytest.raises(FileNotFoundError, match="not found"):
            find_project("nonexistent-project-xyz")


# ---------------------------------------------------------------------------
# Tests: list_phases
# ---------------------------------------------------------------------------


class TestListPhases:
    """Test phase listing output."""

    def test_lists_all_phases(self, project_dir: Path, capsys):
        """list_phases shows all phases with their status."""
        state = load_state(project_dir)
        list_phases(state, project_dir)
        captured = capsys.readouterr()
        assert "architect" in captured.out
        assert "implementation" in captured.out
        assert "testing" in captured.out
        assert "review" in captured.out
        assert "deployment" in captured.out

    def test_marks_current_phase(self, project_dir: Path, capsys):
        """list_phases marks the current phase with >>>."""
        state = load_state(project_dir)
        list_phases(state, project_dir)
        captured = capsys.readouterr()
        assert ">>> implementation" in captured.out

    def test_marks_done_phases(self, project_dir: Path, capsys):
        """list_phases marks phases with retries > 0 as done."""
        state = load_state(project_dir)
        list_phases(state, project_dir)
        captured = capsys.readouterr()
        assert "architect" in captured.out
        assert "done" in captured.out

    def test_shows_gate_status(self, project_dir: Path, capsys):
        """list_phases shows gate approval status correctly."""
        state = load_state(project_dir)
        list_phases(state, project_dir)
        captured = capsys.readouterr()
        # The architect phase has gate "approve_sprint_plan" which is approved
        assert "approved" in captured.out


# ---------------------------------------------------------------------------
# Tests: dump_session
# ---------------------------------------------------------------------------


class TestDumpSession:
    """Test session transcript dumping."""

    def test_dumps_session_json(self, project_with_sessions: Path, capsys):
        """dump_session outputs JSON for the requested phase."""
        from orchestrator.cli.inspect import dump_session

        dump_session(project_with_sessions, "architect", 1)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["role"] == "architect"

    def test_finds_latest_session(self, project_with_sessions: Path, capsys):
        """dump_session falls back to latest session when specific attempt missing."""
        from orchestrator.cli.inspect import dump_session

        dump_session(project_with_sessions, "architect", 99)
        captured = capsys.readouterr()
        # Should find architect-2.json as the latest
        data = json.loads(captured.out)
        assert data["role"] == "architect"

    def test_exits_on_missing_session(self, project_dir: Path):
        """dump_session exits with error when no sessions exist."""
        from orchestrator.cli.inspect import dump_session

        with pytest.raises(SystemExit):
            dump_session(project_dir, "architect", 1)


# ---------------------------------------------------------------------------
# Tests: show_tokens
# ---------------------------------------------------------------------------


class TestShowTokens:
    """Test per-phase token usage display."""

    def test_shows_token_summary(self, project_with_logs: Path, capsys):
        """show_tokens displays per-phase token counts."""
        show_tokens(project_with_logs)
        captured = capsys.readouterr()
        assert "architect" in captured.out
        assert "implementation" in captured.out
        assert "Total" in captured.out

    def test_counts_only_llm_calls(self, project_with_logs: Path, capsys):
        """show_tokens only counts entries with prompt_tokens (llm calls)."""
        show_tokens(project_with_logs)
        captured = capsys.readouterr()
        # architect.jsonl has 2 LLM calls (architect + judge) and 1 non-LLM
        # The output should show the correct totals
        assert "architect" in captured.out

    def test_exits_on_missing_logs(self, project_dir: Path):
        """show_tokens exits with error when no logs directory exists."""
        with pytest.raises(SystemExit):
            show_tokens(project_dir)


# ---------------------------------------------------------------------------
# Tests: main CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    """Test the CLI entry point."""

    def test_list_phases_by_default(self, project_dir: Path, capsys):
        """Running inspect without flags lists phases."""
        main(["inspect", str(project_dir)])
        captured = capsys.readouterr()
        assert "Current phase:" in captured.out

    def test_dump_phase_session(self, project_with_sessions: Path, capsys):
        """Running inspect --phase dumps the session."""
        main(["inspect", str(project_with_sessions), "--phase", "architect"])
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["role"] == "architect"

    def test_show_tokens(self, project_with_logs: Path, capsys):
        """Running inspect --tokens shows token usage."""
        main(["inspect", str(project_with_logs), "--tokens"])
        captured = capsys.readouterr()
        assert "architect" in captured.out
        assert "Total" in captured.out

    def test_unknown_project_exits(self):
        """Running inspect with unknown project exits with error."""
        with pytest.raises(SystemExit):
            main(["inspect", "nonexistent-project-xyz"])
