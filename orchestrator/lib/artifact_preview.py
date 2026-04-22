"""Artifact preview events (M07).

Emit an ``artifact_preview_created`` event after a role finishes writing its
canonical artifact (sprint-plan, TEST_REPORT, REVIEW, DEPLOY, narrative
digest markdown, …). The event carries:

* ``artifact_ref`` — project-relative posix path.
* ``hash`` — sha256 of the full file, so replay can detect "same ref,
  changed content" drift between what the event captured and what the
  current filesystem holds.
* ``bytes`` / ``mime`` — file-size and an extension-driven mime guess.
* ``excerpt`` — bounded text preview (8 KiB head for text/markdown/json,
  2 KiB tail for code files), scrubbed of secrets. Binary artifacts get a
  placeholder instead of raw bytes.
* ``producing_atom_id`` — the phase / atom that wrote the artifact.
* A-9 provenance (``wake_up_hash`` + ``memory_refs``).

The helper is emission-safe: missing files return ``None`` (so engine code
can call it unconditionally per phase without guarding every path), and
path traversal attempts raise ``ArtifactPreviewError``. The helper takes
any event bus that exposes ``emit(type, **fields)`` — the production
``EventBus`` and the test bus both satisfy that.
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Iterable

from orchestrator.lib.memory_palace import memory_event_fields
from orchestrator.lib.scrub import scrub_text


EXCERPT_KIND_TEXT_HEAD: str = "text_head"
EXCERPT_KIND_TEXT_TAIL: str = "text_tail"
EXCERPT_KIND_BINARY_PLACEHOLDER: str = "binary_placeholder"

TEXT_HEAD_BYTES: int = 8 * 1024
CODE_TAIL_BYTES: int = 2 * 1024

_TEXT_HEAD_SUFFIXES: frozenset[str] = frozenset({
    ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".log", ".ini", ".cfg",
})

_CODE_TAIL_SUFFIXES: frozenset[str] = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp",
    ".rb", ".php", ".sh", ".bash", ".zsh", ".sql", ".lua",
})


PHASE_CANONICAL_ARTIFACTS: dict[str, tuple[str, ...]] = {
    "architect": ("sprint-plan.md",),
    "architect_plan": ("sprint-plan.md",),
    "architect_refine": ("sprint-plan.md",),
    "testing": ("TEST_REPORT.md",),
    "review": ("REVIEW.md",),
    "deployment": ("DEPLOY.md",),
}


class ArtifactPreviewError(ValueError):
    """Raised when a preview cannot be safely produced (e.g. traversal)."""


def _project_relative(project_dir: Path, path: Path) -> str:
    resolved_project = project_dir.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_project).as_posix()
    except ValueError as exc:
        raise ArtifactPreviewError(
            f"artifact_ref must resolve inside project_dir: {path}"
        ) from exc


def _resolve_artifact(project_dir: Path, artifact_ref: str) -> Path:
    ref = (artifact_ref or "").strip()
    if not ref:
        raise ArtifactPreviewError("artifact_ref is required")
    candidate = (project_dir / ref)
    resolved_project = project_dir.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_candidate.relative_to(resolved_project)
    except ValueError as exc:
        raise ArtifactPreviewError(
            f"artifact_ref escapes project_dir: {artifact_ref}"
        ) from exc
    return resolved_candidate


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _guess_mime(path: Path) -> str:
    guess, _ = mimetypes.guess_type(path.name)
    return guess or "application/octet-stream"


def _excerpt_for(path: Path, size: int) -> tuple[str, str, bool]:
    """Return (excerpt, excerpt_kind, truncated) for the artifact."""
    suffix = path.suffix.lower()
    if suffix in _TEXT_HEAD_SUFFIXES:
        cap = TEXT_HEAD_BYTES
        with path.open("rb") as handle:
            head = handle.read(cap + 1)
        truncated = len(head) > cap
        head = head[:cap]
        text = _safe_decode(head)
        return scrub_text(text), EXCERPT_KIND_TEXT_HEAD, truncated
    if suffix in _CODE_TAIL_SUFFIXES:
        cap = CODE_TAIL_BYTES
        if size <= cap:
            with path.open("rb") as handle:
                body = handle.read()
            text = _safe_decode(body)
            return scrub_text(text), EXCERPT_KIND_TEXT_TAIL, False
        with path.open("rb") as handle:
            handle.seek(size - cap)
            tail = handle.read(cap)
        text = _safe_decode(tail)
        return scrub_text(text), EXCERPT_KIND_TEXT_TAIL, True
    return (
        f"[binary artifact: {path.name} ({size} bytes)]",
        EXCERPT_KIND_BINARY_PLACEHOLDER,
        size > 0,
    )


def _safe_decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def emit_artifact_preview(
    event_bus: Any,
    project_dir: Path,
    *,
    artifact_ref: str,
    producing_atom_id: str | None = None,
    project_id: str | None = None,
    trigger_event_id: str | None = None,
    source_refs: Iterable[str] | None = None,
) -> dict[str, Any] | None:
    """Emit ``artifact_preview_created`` for a canonical artifact write.

    Returns the emitted event, or ``None`` if the referenced file is absent
    (the common "role short-circuited, no artifact written" path).
    Raises :class:`ArtifactPreviewError` on traversal or empty ref.
    """
    resolved = _resolve_artifact(project_dir, artifact_ref)
    if not resolved.exists() or not resolved.is_file():
        return None

    size = resolved.stat().st_size
    digest = _sha256(resolved)
    mime = _guess_mime(resolved)
    excerpt, excerpt_kind, truncated = _excerpt_for(resolved, size)
    normalized_ref = _project_relative(project_dir, resolved)
    provenance = memory_event_fields(project_id, project_dir)

    payload = {
        "project_id": project_id or project_dir.name,
        "artifact_ref": normalized_ref,
        "producing_atom_id": producing_atom_id or None,
        "hash": digest,
        "bytes": size,
        "mime": mime,
        "excerpt": excerpt,
        "excerpt_kind": excerpt_kind,
        "truncated": truncated,
        "trigger_event_id": trigger_event_id or None,
        "source_refs": [ref for ref in (source_refs or []) if isinstance(ref, str) and ref],
        "wake_up_hash": provenance["wake_up_hash"],
        "memory_refs": list(provenance["memory_refs"]),
    }
    return event_bus.emit("artifact_preview_created", **payload)


def emit_phase_artifact_previews(
    event_bus: Any,
    project_dir: Path,
    phase_name: str,
    *,
    project_id: str | None = None,
    trigger_event_id: str | None = None,
) -> list[dict[str, Any]]:
    """Emit previews for every canonical artifact mapped to ``phase_name``.

    Silently skips missing files so engine integration does not need to
    duplicate the role's knowledge of whether it wrote anything.
    """
    emitted: list[dict[str, Any]] = []
    for ref in PHASE_CANONICAL_ARTIFACTS.get(phase_name, ()):
        event = emit_artifact_preview(
            event_bus,
            project_dir,
            artifact_ref=ref,
            producing_atom_id=phase_name,
            project_id=project_id,
            trigger_event_id=trigger_event_id,
        )
        if event is not None:
            emitted.append(event)
    return emitted
