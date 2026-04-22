"""Drive the full demo ceremony for a prior ``demo_planned`` event (A-10 slice 2b).

Given an already-emitted ``demo_planned`` event, the runner orchestrates:

1. start the configured ``start_command`` (e.g. a dev server) if present;
2. probe the ``route`` until ready;
3. run the configured ``test_command`` (e.g. a Playwright spec);
4. scan the Playwright output directory for artifacts that match the
   ``capture_policy``, hash each, and emit ``demo_artifact_created``;
5. write ``.orchestrator/demos/<demo_id>/metadata.json`` from the real run;
6. emit ``demo_presented`` on success or ``demo_capture_failed`` on error;
7. always terminate the dev server.

The subprocess / readiness-probe / clock shims are injectable so the logic is
deterministic under pytest — tests supply fakes that drop synthesised
artifacts into the output directory without launching a real browser.
"""

from __future__ import annotations

import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol

from orchestrator.lib.demo_capture import (
    CAPTURE_STATUS_FAILED,
    CAPTURE_STATUS_PASSED,
    emit_demo_capture_failed,
    emit_demo_capture_started,
    emit_demo_presented,
    record_demo_artifact,
    write_demo_metadata,
)


DEFAULT_PATTERNS_BY_POLICY: dict[str, tuple[str, ...]] = {
    "gif": ("*.gif",),
    "webm": ("*.webm",),
    "trace": ("trace.zip", "*.zip"),
    "screenshot": ("*.png",),
}


class DemoServerHandle(Protocol):
    """What the runner needs from a long-lived dev-server process."""

    def terminate(self) -> None: ...


ServerLauncher = Callable[[str, Path], DemoServerHandle | None]
"""(command, cwd) → handle (or None if no server needed). Returning None skips readiness probing."""

ReadinessProbe = Callable[[str, float], bool]
"""(url, timeout_s) → True when the route served a 2xx/3xx response."""

TestRunner = Callable[[str, Path, float], tuple[int, str]]
"""(command, cwd, timeout_s) → (exit_code, captured_log_tail)."""


@dataclass
class RunnerDeps:
    start_server: ServerLauncher
    probe_ready: ReadinessProbe
    run_test: TestRunner


class DemoRunnerError(RuntimeError):
    """Raised when the runner hits a condition it cannot continue from."""


class DemoRunner:
    """Execute a planned demo and emit the full capture ceremony."""

    def __init__(
        self,
        event_bus: Any,
        project_dir: Path,
        *,
        deps: RunnerDeps | None = None,
    ) -> None:
        self.bus = event_bus
        self.project_dir = project_dir
        self.deps = deps or default_runner_deps()

    def run(
        self,
        plan_event: dict[str, Any],
        *,
        artifact_source_dir: Path,
        artifact_patterns: Iterable[tuple[str, str]] | None = None,
        base_url: str | None = None,
        start_timeout_s: float = 30.0,
        test_timeout_s: float = 120.0,
        viewport: dict[str, Any] | None = None,
        project_id: str | None = None,
        source_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Drive capture to completion; return the terminal event."""
        if plan_event.get("type") != "demo_planned":
            raise DemoRunnerError(
                f"plan_event must be type 'demo_planned', got {plan_event.get('type')!r}"
            )

        start_command = _string(plan_event.get("start_command"))
        test_command = _string(plan_event.get("test_command"))
        if not test_command:
            raise DemoRunnerError("plan_event.test_command is required to drive capture")

        capture_event = emit_demo_capture_started(
            self.bus,
            self.project_dir,
            plan_event,
            viewport=viewport,
            project_id=project_id,
            source_refs=source_refs,
        )

        server_handle: DemoServerHandle | None = None
        try:
            if start_command:
                server_handle = self.deps.start_server(start_command, self.project_dir)
                probe_url = base_url or _default_probe_url(plan_event.get("route"))
                if probe_url and server_handle is not None:
                    if not self.deps.probe_ready(probe_url, start_timeout_s):
                        return emit_demo_capture_failed(
                            self.bus,
                            self.project_dir,
                            capture_event=capture_event,
                            error=f"start_command route did not become ready at {probe_url} within {start_timeout_s}s",
                            project_id=project_id,
                            source_refs=source_refs,
                        )

            exit_code, log_tail = self.deps.run_test(test_command, self.project_dir, test_timeout_s)

            artifact_refs: list[str] = []
            for kind, artifact_path in _iter_captured_artifacts(
                artifact_source_dir, artifact_patterns, plan_event.get("capture_policy")
            ):
                artifact_event = record_demo_artifact(
                    self.bus,
                    self.project_dir,
                    capture_event=capture_event,
                    artifact_path=artifact_path,
                    kind=kind,
                    test_status=(
                        CAPTURE_STATUS_PASSED if exit_code == 0 else CAPTURE_STATUS_FAILED
                    ),
                    viewport=viewport,
                    project_id=project_id,
                )
                ref = _string(artifact_event.get("artifact_ref"))
                if ref and ref not in artifact_refs:
                    artifact_refs.append(ref)

            if exit_code != 0:
                return emit_demo_capture_failed(
                    self.bus,
                    self.project_dir,
                    capture_event=capture_event,
                    error=f"test_command exited with {exit_code}: {log_tail}".strip(),
                    partial_artifact_refs=artifact_refs,
                    project_id=project_id,
                    source_refs=source_refs,
                )

            metadata_path = write_demo_metadata(
                self.project_dir,
                _string(plan_event.get("demo_id")),
                _build_metadata_payload(
                    plan_event=plan_event,
                    capture_event=capture_event,
                    artifact_refs=artifact_refs,
                    test_status=CAPTURE_STATUS_PASSED,
                    viewport=viewport,
                    log_tail=log_tail,
                ),
            )
            summary_ref = _project_relative(self.project_dir, metadata_path)

            return emit_demo_presented(
                self.bus,
                self.project_dir,
                capture_event=capture_event,
                artifact_refs=artifact_refs or [summary_ref],
                summary_ref=summary_ref,
                test_status=CAPTURE_STATUS_PASSED,
                project_id=project_id,
                source_refs=source_refs,
            )
        except Exception as exc:  # noqa: BLE001 — fan-out into a failure event
            return emit_demo_capture_failed(
                self.bus,
                self.project_dir,
                capture_event=capture_event,
                error=f"{type(exc).__name__}: {exc}",
                project_id=project_id,
                source_refs=source_refs,
            )
        finally:
            if server_handle is not None:
                _safe_terminate(server_handle)


# -- default shims -----------------------------------------------------------


@dataclass
class _PopenHandle:
    proc: subprocess.Popen

    def terminate(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _default_start_server(command: str, cwd: Path) -> DemoServerHandle | None:
    if not command.strip():
        return None
    proc = subprocess.Popen(  # noqa: S603 — command is operator-configured
        shlex.split(command),
        cwd=str(cwd),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return _PopenHandle(proc=proc)


def _default_probe_ready(url: str, timeout_s: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as response:  # noqa: S310 — operator URL
                if 200 <= response.status < 400:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(0.25)
    return False


def _default_run_test(command: str, cwd: Path, timeout_s: float) -> tuple[int, str]:
    try:
        completed = subprocess.run(  # noqa: S603 — command is operator-configured
            shlex.split(command),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        tail = (exc.stderr or exc.stdout or "")[-512:] if isinstance(exc.stderr or exc.stdout, str) else ""
        return (124, f"timeout after {timeout_s}s: {tail}".strip())
    tail = (completed.stderr or completed.stdout or "")[-512:]
    return (completed.returncode, tail)


def default_runner_deps() -> RunnerDeps:
    return RunnerDeps(
        start_server=_default_start_server,
        probe_ready=_default_probe_ready,
        run_test=_default_run_test,
    )


# -- helpers -----------------------------------------------------------------


def _default_probe_url(route: Any) -> str:
    route_str = _string(route)
    if not route_str:
        return ""
    if route_str.startswith(("http://", "https://")):
        return route_str
    prefix = "http://127.0.0.1:5173"
    return prefix + (route_str if route_str.startswith("/") else f"/{route_str}")


def _iter_captured_artifacts(
    source_dir: Path,
    explicit_patterns: Iterable[tuple[str, str]] | None,
    capture_policy: Any,
) -> Iterable[tuple[str, Path]]:
    patterns: list[tuple[str, str]] = []
    if explicit_patterns:
        patterns.extend((kind, glob) for kind, glob in explicit_patterns if kind and glob)
    else:
        policy_list = [
            item for item in (capture_policy or []) if isinstance(item, str) and item.strip()
        ]
        for kind in policy_list or list(DEFAULT_PATTERNS_BY_POLICY.keys()):
            for glob in DEFAULT_PATTERNS_BY_POLICY.get(kind, ()):
                patterns.append((kind, glob))

    if not source_dir.exists():
        return
    seen: set[Path] = set()
    for kind, glob in patterns:
        for candidate in sorted(source_dir.rglob(glob)):
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            yield kind, candidate


def _build_metadata_payload(
    *,
    plan_event: dict[str, Any],
    capture_event: dict[str, Any],
    artifact_refs: list[str],
    test_status: str,
    viewport: dict[str, Any] | None,
    log_tail: str,
) -> dict[str, Any]:
    return {
        "demo_id": _string(plan_event.get("demo_id")),
        "project_id": _string(plan_event.get("project_id")) or _string(capture_event.get("project_id")),
        "task_id": _string(plan_event.get("task_id")) or None,
        "atom_id": _string(plan_event.get("atom_id")) or None,
        "adapter": _string(plan_event.get("adapter")),
        "start_command": _string(plan_event.get("start_command")),
        "test_command": _string(plan_event.get("test_command")),
        "spec_path": _string(plan_event.get("spec_path")),
        "route": _string(plan_event.get("route")),
        "viewport": viewport or capture_event.get("viewport"),
        "test_status": test_status,
        "artifact_refs": list(artifact_refs),
        "plan_event_id": _string(plan_event.get("event_id")),
        "capture_event_id": _string(capture_event.get("event_id")),
        "log_tail": log_tail[-512:] if isinstance(log_tail, str) else "",
        "wake_up_hash": capture_event.get("wake_up_hash"),
        "memory_refs": list(capture_event.get("memory_refs") or []),
    }


def _project_relative(project_dir: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _safe_terminate(handle: DemoServerHandle) -> None:
    try:
        handle.terminate()
    except Exception:  # noqa: BLE001 — best-effort teardown
        return
