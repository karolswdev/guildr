"""Demo capture ceremony events (A-10 slice 2).

Wraps the ``demo_capture_started`` → ``demo_artifact_created`` →
``demo_capture_failed`` / ``demo_presented`` lifecycle around a prior
``demo_planned`` event. The module intentionally does not launch browsers
or start dev servers; it hashes artifacts that already exist on disk, writes
``.orchestrator/demos/<demo_id>/metadata.json``, and emits ledger events
stamped with A-9 memory provenance.

Actually running Playwright, derivating GIFs, or managing long-lived dev
servers is out of scope here — see
``docs/demo-ceremony-and-replay-evidence.md``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.scrub import scrub_text


CAPTURE_STATUS_PASSED: str = "passed"
CAPTURE_STATUS_FAILED: str = "failed"
CAPTURE_STATUS_SKIPPED: str = "skipped"

CAPTURE_STATUSES: frozenset[str] = frozenset({
    CAPTURE_STATUS_PASSED,
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_SKIPPED,
})


class DemoCaptureError(ValueError):
    """Raised when a capture event cannot be safely emitted."""


def demo_dir(project_dir: Path, demo_id: str) -> Path:
    """Return (and create) ``.orchestrator/demos/<demo_id>/`` under project_dir."""
    if not _string(demo_id):
        raise DemoCaptureError("demo_id is required")
    path = project_dir / ".orchestrator" / "demos" / demo_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_sha256(artifact_path: Path) -> str:
    """Return hex sha256 of a file on disk. Raises if missing."""
    resolved = Path(artifact_path)
    if not resolved.exists() or not resolved.is_file():
        raise DemoCaptureError(f"artifact not found: {artifact_path}")
    hasher = hashlib.sha256()
    with resolved.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_demo_metadata(
    project_dir: Path,
    demo_id: str,
    payload: dict[str, Any],
) -> Path:
    """Write ``metadata.json`` under the demo directory and return its path.

    Callers pass the fully-formed payload; the writer only ensures the
    directory exists, serialises deterministically, and returns the path.
    """
    target_dir = demo_dir(project_dir, demo_id)
    target = target_dir / "metadata.json"
    target.write_text(
        json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def emit_demo_capture_started(
    event_bus: Any,
    project_dir: Path,
    plan_event: dict[str, Any],
    *,
    viewport: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Emit ``demo_capture_started`` tied to a prior ``demo_planned`` event."""
    _require_plan_event(plan_event, allowed_types=("demo_planned",))

    demo_id = _string(plan_event.get("demo_id"))
    adapter = _string(plan_event.get("adapter"))
    plan_event_id = _string(plan_event.get("event_id"))

    refs = _with_ref(source_refs, f"event:{plan_event_id}") if plan_event_id else _dedupe(list(source_refs or []))
    provenance = memory_event_fields(project_id, project_dir)

    return event_bus.emit(
        "demo_capture_started",
        project_id=_string(plan_event.get("project_id")) or project_id or project_dir.name,
        demo_id=demo_id,
        task_id=_string(plan_event.get("task_id")) or None,
        atom_id=_string(plan_event.get("atom_id")) or None,
        adapter=adapter,
        start_command=_string(plan_event.get("start_command")),
        test_command=_string(plan_event.get("test_command")),
        spec_path=_string(plan_event.get("spec_path")),
        route=_string(plan_event.get("route")),
        viewport=_clean_viewport(viewport),
        source_refs=refs,
        artifact_refs=[],
        wake_up_hash=provenance["wake_up_hash"],
        memory_refs=list(provenance["memory_refs"]),
    )


def record_demo_artifact(
    event_bus: Any,
    project_dir: Path,
    *,
    capture_event: dict[str, Any],
    artifact_path: Path | str,
    kind: str,
    artifact_ref: str | None = None,
    test_status: str | None = None,
    viewport: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Hash ``artifact_path`` and emit ``demo_artifact_created`` for it.

    ``artifact_ref`` defaults to the path relative to ``project_dir`` when
    possible (so PWA replay can resolve it through the bounded artifact route).
    """
    _require_plan_event(capture_event, allowed_types=("demo_capture_started",))
    kind_clean = _string(kind)
    if not kind_clean:
        raise DemoCaptureError("kind is required")
    if test_status is not None and test_status not in CAPTURE_STATUSES:
        raise DemoCaptureError(f"unknown test_status: {test_status!r}")

    path = Path(artifact_path)
    digest = artifact_sha256(path)
    ref = _string(artifact_ref) or _project_relative_ref(project_dir, path)

    demo_id = _string(capture_event.get("demo_id"))
    adapter = _string(capture_event.get("adapter"))
    capture_event_id = _string(capture_event.get("event_id"))

    refs = _with_ref(source_refs, f"event:{capture_event_id}") if capture_event_id else _dedupe(list(source_refs or []))
    provenance = memory_event_fields(project_id, project_dir)

    return event_bus.emit(
        "demo_artifact_created",
        project_id=_string(capture_event.get("project_id")) or project_id or project_dir.name,
        demo_id=demo_id,
        task_id=_string(capture_event.get("task_id")) or None,
        atom_id=_string(capture_event.get("atom_id")) or None,
        adapter=adapter,
        kind=kind_clean,
        artifact_ref=ref,
        artifact_sha256=digest,
        artifact_bytes=path.stat().st_size,
        test_status=_string(test_status) or None,
        spec_path=_string(capture_event.get("spec_path")),
        route=_string(capture_event.get("route")),
        viewport=_clean_viewport(viewport or capture_event.get("viewport")),
        source_refs=refs,
        artifact_refs=[ref],
        wake_up_hash=provenance["wake_up_hash"],
        memory_refs=list(provenance["memory_refs"]),
    )


def emit_demo_capture_failed(
    event_bus: Any,
    project_dir: Path,
    *,
    capture_event: dict[str, Any],
    error: str,
    partial_artifact_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Emit ``demo_capture_failed`` when a run started but did not complete."""
    _require_plan_event(capture_event, allowed_types=("demo_capture_started",))
    if not _string(error):
        raise DemoCaptureError("error is required")

    capture_event_id = _string(capture_event.get("event_id"))
    refs = _with_ref(source_refs, f"event:{capture_event_id}") if capture_event_id else _dedupe(list(source_refs or []))
    provenance = memory_event_fields(project_id, project_dir)

    return event_bus.emit(
        "demo_capture_failed",
        project_id=_string(capture_event.get("project_id")) or project_id or project_dir.name,
        demo_id=_string(capture_event.get("demo_id")),
        task_id=_string(capture_event.get("task_id")) or None,
        atom_id=_string(capture_event.get("atom_id")) or None,
        adapter=_string(capture_event.get("adapter")),
        spec_path=_string(capture_event.get("spec_path")),
        route=_string(capture_event.get("route")),
        error=scrub_text(error),
        source_refs=refs,
        artifact_refs=_dedupe(list(partial_artifact_refs or [])),
        wake_up_hash=provenance["wake_up_hash"],
        memory_refs=list(provenance["memory_refs"]),
    )


def emit_demo_presented(
    event_bus: Any,
    project_dir: Path,
    *,
    capture_event: dict[str, Any],
    artifact_refs: list[str],
    summary_ref: str | None = None,
    test_status: str = CAPTURE_STATUS_PASSED,
    source_refs: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Emit ``demo_presented`` to mark the demo card ready for the UI."""
    _require_plan_event(capture_event, allowed_types=("demo_capture_started",))
    if test_status not in CAPTURE_STATUSES:
        raise DemoCaptureError(f"unknown test_status: {test_status!r}")
    refs_out = _dedupe(list(artifact_refs or []))
    if not refs_out:
        raise DemoCaptureError("artifact_refs is required for demo_presented")

    capture_event_id = _string(capture_event.get("event_id"))
    provenance_refs = _with_ref(source_refs, f"event:{capture_event_id}") if capture_event_id else _dedupe(list(source_refs or []))
    provenance = memory_event_fields(project_id, project_dir)

    return event_bus.emit(
        "demo_presented",
        project_id=_string(capture_event.get("project_id")) or project_id or project_dir.name,
        demo_id=_string(capture_event.get("demo_id")),
        task_id=_string(capture_event.get("task_id")) or None,
        atom_id=_string(capture_event.get("atom_id")) or None,
        adapter=_string(capture_event.get("adapter")),
        test_status=test_status,
        spec_path=_string(capture_event.get("spec_path")),
        route=_string(capture_event.get("route")),
        summary_ref=_string(summary_ref) or None,
        source_refs=provenance_refs,
        artifact_refs=refs_out,
        wake_up_hash=provenance["wake_up_hash"],
        memory_refs=list(provenance["memory_refs"]),
    )


def _require_plan_event(event: Any, *, allowed_types: tuple[str, ...]) -> None:
    if not isinstance(event, dict):
        raise DemoCaptureError("capture/plan event must be a dict")
    event_type = _string(event.get("type"))
    if event_type not in allowed_types:
        raise DemoCaptureError(
            f"expected event type in {allowed_types!r}, got {event_type!r}"
        )
    if not _string(event.get("demo_id")):
        raise DemoCaptureError("event is missing demo_id")
    if not _string(event.get("event_id")):
        raise DemoCaptureError("event is missing event_id")


def _project_relative_ref(project_dir: Path, artifact_path: Path) -> str:
    try:
        rel = artifact_path.resolve().relative_to(project_dir.resolve())
    except ValueError:
        return str(artifact_path)
    return rel.as_posix()


def _clean_viewport(viewport: Any) -> dict[str, Any] | None:
    if not isinstance(viewport, dict):
        return None
    cleaned: dict[str, Any] = {}
    for key in ("name", "width", "height"):
        if key in viewport and viewport[key] not in (None, ""):
            cleaned[key] = viewport[key]
    return cleaned or None


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _with_ref(values: list[str] | None, ref: str) -> list[str]:
    combined = list(values or [])
    if ref and ref not in combined:
        combined.append(ref)
    return _dedupe(combined)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
