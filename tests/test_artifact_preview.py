"""Tests for artifact preview events (M07)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrator.lib.artifact_preview import (
    ArtifactPreviewError,
    CODE_TAIL_BYTES,
    EXCERPT_KIND_BINARY_PLACEHOLDER,
    EXCERPT_KIND_TEXT_HEAD,
    EXCERPT_KIND_TEXT_TAIL,
    PHASE_CANONICAL_ARTIFACTS,
    TEXT_HEAD_BYTES,
    emit_artifact_preview,
    emit_phase_artifact_previews,
)
from orchestrator.lib.events import EventBus


def _full_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    return hasher.hexdigest()


def test_emit_artifact_preview_hashes_full_file_and_caps_text_excerpt(tmp_path: Path) -> None:
    bus = EventBus()
    report = tmp_path / "TEST_REPORT.md"
    body = "# Report\n\n" + ("line of evidence\n" * 4000)
    report.write_text(body, encoding="utf-8")

    event = emit_artifact_preview(
        bus,
        tmp_path,
        artifact_ref="TEST_REPORT.md",
        producing_atom_id="testing",
        project_id="proj-1",
        trigger_event_id="trigger-xyz",
        source_refs=["qwendea.md"],
    )

    assert event is not None
    assert event["type"] == "artifact_preview_created"
    assert event["artifact_ref"] == "TEST_REPORT.md"
    assert event["producing_atom_id"] == "testing"
    assert event["project_id"] == "proj-1"
    assert event["trigger_event_id"] == "trigger-xyz"
    assert event["source_refs"] == ["qwendea.md"]
    assert event["hash"] == _full_sha256(report)
    assert event["bytes"] == report.stat().st_size
    assert event["mime"] == "text/markdown"
    assert event["excerpt_kind"] == EXCERPT_KIND_TEXT_HEAD
    assert event["truncated"] is True
    assert len(event["excerpt"].encode("utf-8")) <= TEXT_HEAD_BYTES
    assert "wake_up_hash" in event
    assert "memory_refs" in event


def test_emit_artifact_preview_uses_tail_for_code(tmp_path: Path) -> None:
    bus = EventBus()
    source = tmp_path / "module.py"
    prefix = "# ignored header\n" * 500
    sentinel = "def target() -> int:\n    return 42\n"
    source.write_text(prefix + sentinel, encoding="utf-8")

    event = emit_artifact_preview(
        bus,
        tmp_path,
        artifact_ref="module.py",
        producing_atom_id="implementation",
    )

    assert event is not None
    assert event["excerpt_kind"] == EXCERPT_KIND_TEXT_TAIL
    assert event["truncated"] is True
    assert len(event["excerpt"].encode("utf-8")) <= CODE_TAIL_BYTES
    assert sentinel.strip() in event["excerpt"]


def test_emit_artifact_preview_small_code_not_truncated(tmp_path: Path) -> None:
    bus = EventBus()
    source = tmp_path / "tiny.py"
    source.write_text("print('hi')\n", encoding="utf-8")

    event = emit_artifact_preview(bus, tmp_path, artifact_ref="tiny.py")

    assert event is not None
    assert event["excerpt_kind"] == EXCERPT_KIND_TEXT_TAIL
    assert event["truncated"] is False
    assert "print('hi')" in event["excerpt"]


def test_emit_artifact_preview_binary_returns_placeholder(tmp_path: Path) -> None:
    bus = EventBus()
    blob = tmp_path / "image.png"
    blob.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048)

    event = emit_artifact_preview(bus, tmp_path, artifact_ref="image.png")

    assert event is not None
    assert event["excerpt_kind"] == EXCERPT_KIND_BINARY_PLACEHOLDER
    assert "binary artifact" in event["excerpt"]
    assert event["mime"].startswith("image/")
    assert event["hash"] == _full_sha256(blob)


def test_emit_artifact_preview_missing_file_returns_none(tmp_path: Path) -> None:
    bus = EventBus()
    assert emit_artifact_preview(bus, tmp_path, artifact_ref="nope.md") is None


def test_emit_artifact_preview_rejects_path_traversal(tmp_path: Path) -> None:
    bus = EventBus()
    outside = tmp_path.parent / "escape.md"
    outside.write_text("secret", encoding="utf-8")
    try:
        with pytest.raises(ArtifactPreviewError):
            emit_artifact_preview(bus, tmp_path, artifact_ref="../escape.md")
    finally:
        outside.unlink(missing_ok=True)


def test_emit_artifact_preview_rejects_empty_ref(tmp_path: Path) -> None:
    bus = EventBus()
    with pytest.raises(ArtifactPreviewError):
        emit_artifact_preview(bus, tmp_path, artifact_ref="   ")


def test_emit_artifact_preview_scrubs_secrets_in_excerpt(tmp_path: Path) -> None:
    bus = EventBus()
    plan = tmp_path / "sprint-plan.md"
    plan.write_text(
        "step 1\nAUTH_TOKEN=STRIPE_LIVE_KEY_REDACTED_SAMPLE\nstep 3\n",
        encoding="utf-8",
    )
    event = emit_artifact_preview(bus, tmp_path, artifact_ref="sprint-plan.md")

    assert event is not None
    assert "STRIPE_LIVE_KEY_REDACTED_SAMPLE" not in event["excerpt"]


def test_emit_phase_artifact_previews_emits_only_present_files(tmp_path: Path) -> None:
    bus = EventBus()
    (tmp_path / "TEST_REPORT.md").write_text("all passing\n", encoding="utf-8")

    emitted = emit_phase_artifact_previews(
        bus,
        tmp_path,
        "testing",
        project_id="proj-x",
        trigger_event_id="trigger-1",
    )

    assert len(emitted) == 1
    assert emitted[0]["artifact_ref"] == "TEST_REPORT.md"
    assert emitted[0]["producing_atom_id"] == "testing"


def test_emit_phase_artifact_previews_unknown_phase_is_noop(tmp_path: Path) -> None:
    bus = EventBus()
    emitted = emit_phase_artifact_previews(bus, tmp_path, "memory_refresh")
    assert emitted == []


def test_phase_artifact_mapping_covers_expected_roles() -> None:
    expected_refs = {
        "architect": "sprint-plan.md",
        "architect_plan": "sprint-plan.md",
        "architect_refine": "sprint-plan.md",
        "testing": "TEST_REPORT.md",
        "review": "REVIEW.md",
        "deployment": "DEPLOY.md",
    }
    for phase, ref in expected_refs.items():
        assert ref in PHASE_CANONICAL_ARTIFACTS[phase]
