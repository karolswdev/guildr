"""Tests for orchestrator.lib.state."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.lib.state import State


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    return tmp_path


@pytest.fixture
def state(tmp_project: Path) -> State:
    """Create a State instance pointing at tmp_project."""
    return State(tmp_project)


class TestSaveLoad:
    """Test State.save() and State.load()."""

    def test_save_and_load_round_trip(self, state: State, tmp_project: Path):
        state.current_phase = "architect"
        state.sessions = {"architect": "sess-1"}
        state.retries = {"architect": 1}
        state.gates_approved = {"sprint_plan": True}
        state.save()

        loaded = State(tmp_project)
        loaded.load()

        assert loaded.current_phase == "architect"
        assert loaded.sessions == {"architect": "sess-1"}
        assert loaded.retries == {"architect": 1}
        assert loaded.gates_approved == {"sprint_plan": True}

    def test_save_creates_orchestrator_dir(self, state: State, tmp_project: Path):
        state.save()
        assert (tmp_project / ".orchestrator").is_dir()
        assert (tmp_project / ".orchestrator" / "state.json").exists()

    def test_save_is_atomic(self, state: State, tmp_project: Path):
        """Verify atomic write: tmp file is renamed, not copied."""
        state.save()
        # .tmp should not persist after successful save
        assert not (tmp_project / ".orchestrator" / "state.json.tmp").exists()
        assert (tmp_project / ".orchestrator" / "state.json").exists()

    def test_save_atomic_on_replace_failure(self, state: State, tmp_project: Path):
        """If os.replace raises, no corrupted file should remain."""
        state.current_phase = "architect"
        state.save()

        # Now mock os.replace to raise on the second save
        with patch("orchestrator.lib.state.os.replace", side_effect=OSError("disk full")):
            state.current_phase = "coder"
            with pytest.raises(OSError):
                state.save()

        # Original file should be untouched
        data = json.loads((tmp_project / ".orchestrator" / "state.json").read_text())
        assert data["current_phase"] == "architect"

    def test_save_atomic_no_tmp_left_on_failure(self, state: State, tmp_project: Path):
        """If os.replace raises, the .tmp file should be cleaned up."""
        state.current_phase = "architect"
        state.save()

        with patch("orchestrator.lib.state.os.replace", side_effect=OSError("disk full")):
            state.current_phase = "coder"
            with pytest.raises(OSError):
                state.save()

        # .tmp should be cleaned up
        assert not (tmp_project / ".orchestrator" / "state.json.tmp").exists()


class TestLoadTolerance:
    """Test State.load() tolerance for edge cases."""

    def test_load_missing_file(self, state: State):
        """Load with no state file should leave defaults."""
        state.load()
        assert state.current_phase is None
        assert state.sessions == {}
        assert state.retries == {}
        assert state.gates_approved == {}

    def test_load_empty_file(self, tmp_project: Path):
        """Load with empty file should raise JSONDecodeError (expected)."""
        state_file = tmp_project / ".orchestrator" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("", encoding="utf-8")
        state = State(tmp_project)
        with pytest.raises(json.JSONDecodeError):
            state.load()

    def test_load_partial_json(self, state: State, tmp_project: Path):
        """Load with missing keys should fill defaults."""
        state_file = tmp_project / ".orchestrator" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps({"current_phase": "architect"}),
            encoding="utf-8",
        )
        state.load()
        assert state.current_phase == "architect"
        assert state.sessions == {}
        assert state.retries == {}
        assert state.gates_approved == {}

    def test_load_completely_missing_keys(self, state: State, tmp_project: Path):
        """Load with empty object should use all defaults."""
        state_file = tmp_project / ".orchestrator" / "state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text("{}", encoding="utf-8")
        state.load()
        assert state.current_phase is None
        assert state.sessions == {}
        assert state.retries == {}
        assert state.gates_approved == {}


class TestReadWriteFile:
    """Test State.read_file() and State.write_file()."""

    def test_write_and_read_file(self, state: State, tmp_project: Path):
        state.write_file("qwendea.md", "# My Project\n\nDescription here.")
        content = state.read_file("qwendea.md")
        assert content == "# My Project\n\nDescription here."

    def test_write_file_creates_subdirs(self, state: State, tmp_project: Path):
        state.write_file("sub/dir/file.txt", "hello")
        assert (tmp_project / "sub" / "dir" / "file.txt").exists()
        assert state.read_file("sub/dir/file.txt") == "hello"

    def test_write_file_overwrites(self, state: State, tmp_project: Path):
        state.write_file("test.txt", "v1")
        state.write_file("test.txt", "v2")
        assert state.read_file("test.txt") == "v2"

    def test_read_file_not_found(self, state: State):
        with pytest.raises(FileNotFoundError):
            state.read_file("nonexistent.md")
