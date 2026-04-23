"""Integration test: engine triggers consult at the 7 phase sites (A-8.2)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.lib.config import Config
from orchestrator.lib.discussion import discussion_log_path


def _setup_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / "qwendea.md").write_text("test brief", encoding="utf-8")
    (project / "FOUNDING_TEAM.json").write_text(
        json.dumps({
            "personas": [
                {"name": "Founder", "perspective": "business owner",
                 "mandate": "Guard scope.", "veto_scope": "scope drift", "turn_order": 1},
                {"name": "End User", "perspective": "client",
                 "mandate": "Represent usability.", "veto_scope": "usability regression", "turn_order": 2},
            ]
        }),
        encoding="utf-8",
    )
    return project


def test_consult_founding_team_runs_at_trigger(tmp_path: Path) -> None:
    from orchestrator.engine import Orchestrator

    project = _setup_project(tmp_path)
    cfg = Config(llama_server_url="http://127.0.0.1:8080", project_dir=project)
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = cfg
    orch._events = MagicMock()

    orch._consult_founding_team("architect_plan_done", "plan landed")

    log = discussion_log_path(project).read_text(encoding="utf-8").splitlines()
    assert len(log) == 3  # 2 persona statements + 1 convergence
    first = json.loads(log[0])
    assert first["metadata"]["trigger_tag"] == "architect_plan_done"


def test_consult_skipped_when_personas_missing(tmp_path: Path) -> None:
    from orchestrator.engine import Orchestrator

    project = tmp_path / "project"
    project.mkdir()
    cfg = Config(llama_server_url="http://127.0.0.1:8080", project_dir=project)
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = cfg
    orch._events = MagicMock()

    orch._consult_founding_team("coder_done", "coder done")
    assert not discussion_log_path(project).exists()


def test_consult_skipped_when_trigger_disabled(tmp_path: Path) -> None:
    from orchestrator.engine import Orchestrator

    project = _setup_project(tmp_path)
    cfg = Config(llama_server_url="http://127.0.0.1:8080", project_dir=project)
    cfg.consult.disabled_triggers = {"coder_done"}
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = cfg
    orch._events = MagicMock()

    orch._consult_founding_team("coder_done", "coder done")
    assert not discussion_log_path(project).exists()

    orch._consult_founding_team("reviewer_done", "review posted")
    assert discussion_log_path(project).exists()


def test_consult_never_raises_on_internal_errors(tmp_path: Path) -> None:
    from orchestrator.engine import Orchestrator

    project = _setup_project(tmp_path)
    # Corrupt the personas file — consult must swallow the parse error.
    (project / "FOUNDING_TEAM.json").write_text("{not json", encoding="utf-8")
    cfg = Config(llama_server_url="http://127.0.0.1:8080", project_dir=project)
    orch = Orchestrator.__new__(Orchestrator)
    orch.config = cfg
    orch._events = MagicMock()

    # Should not raise, should not write entries.
    orch._consult_founding_team("coder_done", "coder done")
    assert not discussion_log_path(project).exists()
