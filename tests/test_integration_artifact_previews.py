"""Integration test for M07 artifact-preview emission.

Drives the full dry-run pipeline and asserts every canonical artifact
write produces an ``artifact_preview_created`` event with a matching
sha256, the expected ``producing_atom_id``, and A-9 provenance stamped.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrator.engine import Orchestrator
from orchestrator.lib.config import Config
from orchestrator.lib.events import EventBus


class CapturingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

    def emit(self, type: str, **fields):  # type: ignore[override]
        event = super().emit(type, **fields)
        self.events.append(event)
        return event


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    pd = tmp_path / "proj"
    pd.mkdir()
    (pd / "qwendea.md").write_text(
        "# Project: Tiny CLI\n\nBuild a one-command CLI that prints hello.\n"
    )
    return pd


@pytest.fixture
def config(project_dir: Path) -> Config:
    return Config(
        llama_server_url="http://unused-in-dry-run",
        project_dir=project_dir,
        require_human_approval=False,
        max_retries=2,
        architect_max_passes=2,
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_dry_run_pipeline_emits_artifact_preview_events(
    config: Config, project_dir: Path
) -> None:
    bus = CapturingBus()
    Orchestrator(config=config, dry_run=True, events=bus).run()

    previews = [e for e in bus.events if e["type"] == "artifact_preview_created"]
    by_ref: dict[str, list[dict]] = {}
    for event in previews:
        by_ref.setdefault(event["artifact_ref"], []).append(event)

    expected_phase_by_ref = {
        "sprint-plan.md": {"architect", "architect_plan", "architect_refine"},
        "TEST_REPORT.md": {"testing"},
        "REVIEW.md": {"review"},
        "DEPLOY.md": {"deployment"},
    }

    for ref, allowed_phases in expected_phase_by_ref.items():
        assert ref in by_ref, f"no artifact_preview_created for {ref}"
        latest = by_ref[ref][-1]
        artifact_path = project_dir / ref
        assert latest["hash"] == _sha256(artifact_path), (
            f"{ref} preview hash does not match current file bytes"
        )
        assert latest["bytes"] == artifact_path.stat().st_size
        assert latest["producing_atom_id"] in allowed_phases, (
            f"{ref} producing_atom_id={latest['producing_atom_id']!r} "
            f"not in {allowed_phases}"
        )
        assert "wake_up_hash" in latest
        assert "memory_refs" in latest

    narrator_previews = [
        e for e in previews if e.get("producing_atom_id") == "narrator"
    ]
    assert narrator_previews, (
        "expected at least one narrative-digest artifact_preview_created event "
        "(producing_atom_id='narrator')"
    )
    for event in narrator_previews:
        assert event["artifact_ref"].endswith(".md")
        full_path = project_dir / event["artifact_ref"]
        assert full_path.exists(), f"narrator preview references missing file {full_path}"
        assert event["hash"] == _sha256(full_path)
