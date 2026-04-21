"""Bridge between the synchronous Orchestrator engine and the async PWA.

The orchestrator engine is sync end-to-end (blocking HTTP to llama-server,
file I/O on the project dir). Running it inside the FastAPI event loop
would freeze every other request, so we hand it off to a worker thread via
``asyncio.to_thread``.

Events the engine emits through ``orchestrator.lib.events.EventBus`` need
to land in the per-project ``SimpleEventBus`` that the SSE route reads
from. ``BridgingEventBus`` does that forwarding — when the engine emits
``("phase_start", name="architect", attempt=0)``, the bridge re-emits
the same payload on the project's SSE bus so the PWA's Progress view
sees it live.

Concurrency model: one background run per project. ``start`` returns
immediately with whether a new run was scheduled; if a run is already
in flight for that project, it returns ``False`` instead of stacking
runs on top of each other.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any

from orchestrator.engine import Orchestrator, PhaseFailure
from orchestrator.lib.config import Config
from orchestrator.lib.events import EventBus
from web.backend.routes.gates import get_gate_store
from web.backend.routes.stream import EventStore, SimpleEventBus, get_event_store

logger = logging.getLogger(__name__)


class BridgingEventBus(EventBus):
    """EventBus that mirrors every emit onto a SimpleEventBus.

    Subclasses the engine's EventBus so the engine can keep using its
    existing interface; the override fans the same payload out to a
    SimpleEventBus consumed by the SSE stream route.
    """

    def __init__(self, sink: SimpleEventBus) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, type: str, **fields: Any) -> dict[str, Any]:  # noqa: A002 — match parent signature
        event = super().emit(type, **fields)
        try:
            self._sink.emit(type, **{key: value for key, value in event.items() if key != "type"})
        except Exception:
            logger.debug("SSE sink emit failed", exc_info=True)
        return event


class RunRegistry:
    """Tracks in-flight orchestrator runs to prevent double-starts.

    Keyed by project_id. A project is "active" while its background
    thread is alive. Cleanup happens lazily on the next start attempt.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def is_active(self, project_id: str) -> bool:
        with self._lock:
            t = self._threads.get(project_id)
            if t is None:
                return False
            if not t.is_alive():
                del self._threads[project_id]
                return False
            return True

    def register(self, project_id: str, thread: threading.Thread) -> None:
        with self._lock:
            self._threads[project_id] = thread


_registry = RunRegistry()


def get_run_registry() -> RunRegistry:
    return _registry


def _build_llm(dry_run: bool, llama_url: str) -> object:
    """Return a sync LLM client compatible with the engine's fake_llm slot.

    Dry-run uses the same content-aware fake the CLI uses so the PWA
    demo and the integration tests follow identical code paths.
    """
    if dry_run:
        from orchestrator.cli.run import _build_dry_run_llm
        return _build_dry_run_llm()
    from orchestrator.lib.llm import LLMClient
    return LLMClient(base_url=llama_url)


def _build_pool_from_env() -> object | None:
    """If ``ORCHESTRATOR_CONFIG`` points to a YAML with an ``endpoints:``
    block, build and return an ``UpstreamPool``. Else ``None``.

    Lets the PWA live path opt into multi-endpoint routing without
    changing the single-``LLAMA_URL`` demo contract.
    """
    path_str = os.environ.get("ORCHESTRATOR_CONFIG")
    if not path_str:
        return None
    from orchestrator.lib.endpoints import build_pool, load_endpoints_from_yaml
    cfg = load_endpoints_from_yaml(Path(path_str))
    if cfg is None:
        return None
    return build_pool(cfg)


def _build_endpoints_cfg_from_env() -> object | None:
    """Return the parsed ``EndpointsConfig`` if ``ORCHESTRATOR_CONFIG`` is set.

    The pool and the opencode session runners both derive from the
    same YAML; returning the parsed config here keeps ``_run_orchestrator``
    from parsing it twice.
    """
    path_str = os.environ.get("ORCHESTRATOR_CONFIG")
    if not path_str:
        return None
    from orchestrator.lib.endpoints import load_endpoints_from_yaml
    return load_endpoints_from_yaml(Path(path_str))


def _resolve_project_dir(project_id: str) -> Path:
    """Where the orchestrator should land its artifacts for this project.

    Mirrors the layout used by the in-memory ProjectStore: each project
    gets its own subdirectory under ORCHESTRATOR_PROJECTS_DIR (default
    /tmp/orchestrator-projects).
    """
    base = Path(os.environ.get("ORCHESTRATOR_PROJECTS_DIR", "/tmp/orchestrator-projects"))
    pd = base / project_id
    pd.mkdir(parents=True, exist_ok=True)
    return pd


def _ensure_qwendea(project_dir: Path, idea: str | None) -> None:
    """Seed qwendea.md from the project's initial idea if it's missing.

    Source of truth, in order:
      1. an explicit ``idea`` arg (passed in from the route)
      2. ``initial_idea.txt`` written by ProjectStore.create
      3. a generic placeholder

    Only writes when qwendea.md doesn't already exist — never overwrites
    a real project's seed doc.
    """
    qf = project_dir / "qwendea.md"
    if qf.exists():
        return
    if not idea:
        idea_file = project_dir / "initial_idea.txt"
        if idea_file.exists():
            idea = idea_file.read_text(encoding="utf-8")
    body = idea.strip() if idea else "Build something useful."
    qf.write_text(f"# Project\n\n{body}\n")


def _run_orchestrator(
    project_id: str,
    project_dir: Path,
    bus: SimpleEventBus,
    dry_run: bool,
    llama_url: str,
    *,
    start_at: str | None = None,
    require_human_approval: bool = False,
) -> None:
    """Run the engine to completion in this thread, mirroring events to ``bus``.

    Any exception is logged and surfaced to the SSE bus as a ``run_error``
    event so the PWA can show it instead of silently failing.
    """
    try:
        bridge = BridgingEventBus(bus)
        config = Config(
            llama_server_url=llama_url,
            project_dir=project_dir,
            architect_max_passes=5,
            require_human_approval=require_human_approval,
        )
        endpoints_cfg = None if dry_run else _build_endpoints_cfg_from_env()
        gate_registry = get_gate_store().ensure(project_id)
        orch_kwargs: dict[str, Any] = {
            "config": config,
            "events": bridge,
            "gate_registry": gate_registry,
        }
        if endpoints_cfg is not None:
            from orchestrator.cli.run import _build_opencode_session_runners
            from orchestrator.lib.endpoints import build_pool
            orch_kwargs["pool"] = build_pool(endpoints_cfg)  # type: ignore[arg-type]
            orch_kwargs["session_runners"] = _build_opencode_session_runners(
                endpoints_cfg, project_dir
            )
        else:
            orch_kwargs["fake_llm"] = _build_llm(dry_run, llama_url)
        orch = Orchestrator(**orch_kwargs)
        bus.emit("run_started", project_id=project_id, dry_run=dry_run, start_at=start_at)
        orch.run(start_at=start_at)
        bus.emit("run_complete", project_id=project_id)
    except PhaseFailure as e:
        logger.warning("Run failed for %s: %s", project_id, e)
        bus.emit("run_error", project_id=project_id, error=str(e), kind="phase_failure")
    except Exception as e:
        logger.exception("Unexpected error during run for %s", project_id)
        bus.emit("run_error", project_id=project_id, error=str(e), kind="exception")


def start_run(
    project_id: str,
    initial_idea: str | None = None,
    *,
    dry_run: bool | None = None,
    llama_url: str | None = None,
    event_store: EventStore | None = None,
    start_at: str | None = None,
    require_human_approval: bool = False,
) -> bool:
    """Schedule a background orchestrator run for ``project_id``.

    Returns True if a new run was started, False if one was already
    in flight for this project. ``dry_run`` defaults to True unless
    ``LLAMA_SERVER_URL`` is set in the environment.

    ``require_human_approval`` is a per-run opt-in. The default is False —
    the PWA is an idle-RPG touch surface, not a "human is watching so gate
    everything" trigger. Callers that want attended runs pass True.
    """
    if event_store is None:
        event_store = get_event_store()

    if _registry.is_active(project_id):
        return False

    project_dir = _resolve_project_dir(project_id)
    _ensure_qwendea(project_dir, initial_idea)

    if dry_run is None:
        dry_run = "LLAMA_SERVER_URL" not in os.environ
    if llama_url is None:
        llama_url = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8080")

    bus = event_store.get_or_create(project_id)

    thread = threading.Thread(
        target=_run_orchestrator,
        args=(project_id, project_dir, bus, dry_run, llama_url),
        kwargs={"start_at": start_at, "require_human_approval": require_human_approval},
        name=f"guildr-run-{project_id[:8]}",
        daemon=True,
    )
    _registry.register(project_id, thread)
    thread.start()
    return True


async def start_run_async(
    project_id: str,
    initial_idea: str | None = None,
    **kwargs: Any,
) -> bool:
    """Async-friendly wrapper for FastAPI route handlers.

    The actual run still happens on a daemon thread — this wrapper just
    yields back to the event loop so the route returns immediately.
    """
    return await asyncio.to_thread(start_run, project_id, initial_idea, **kwargs)
