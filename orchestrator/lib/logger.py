"""Structured JSON logging for the orchestrator.

Provides per-phase JSONL log files and LLM call instrumentation.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional


def _default_ts() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


class JsonFormatter(logging.Formatter):
    """Format log records as JSON lines."""

    def __init__(
        self,
        phase: str = "",
        task_id: str = "",
        session_id: str = "",
    ) -> None:
        super().__init__()
        self._phase = phase
        self._task_id = task_id
        self._session_id = session_id

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": getattr(record, "ts", _default_ts()),
            "level": record.levelname,
            "phase": getattr(record, "phase", self._phase),
            "task_id": getattr(record, "task_id", self._task_id),
            "session_id": getattr(record, "session_id", self._session_id),
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
            "logger": record.name,
        }
        if hasattr(record, "exception") and record.exception:
            entry["exception"] = record.exception
        if hasattr(record, "prompt_tokens"):
            entry["prompt_tokens"] = record.prompt_tokens
        if hasattr(record, "completion_tokens"):
            entry["completion_tokens"] = record.completion_tokens
        if hasattr(record, "reasoning_tokens"):
            entry["reasoning_tokens"] = record.reasoning_tokens
        if hasattr(record, "latency_ms"):
            entry["latency_ms"] = record.latency_ms
        if hasattr(record, "request_id"):
            entry["request_id"] = record.request_id
        if record.levelno >= logging.ERROR and record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class PhaseFileHandler(logging.Handler):
    """Write log records to a per-phase JSONL file."""

    def __init__(self, log_dir: Path, phase: str) -> None:
        super().__init__()
        self._log_dir = log_dir
        self._phase = phase
        self._path = log_dir / f"{phase}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            fmt = JsonFormatter(
                phase=self._phase,
                task_id=getattr(record, "task_id", ""),
                session_id=getattr(record, "session_id", ""),
            )
            line = fmt.format(record) + "\n"
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            self.handleError(record)


def setup_phase_logger(
    project_dir: Path,
    phase: str,
    level: int = logging.INFO,
    task_id: str = "",
    session_id: str | None = None,
    *,
    console: bool = True,
) -> logging.Logger:
    """Set up a structured logger for a specific phase.

    Creates a logger that writes JSON lines to
    ``.orchestrator/logs/<phase>.jsonl`` in the project directory.

    Args:
        project_dir: Root of the project directory.
        phase: Phase name (e.g. ``"architect"``).
        level: Logging level.
        task_id: Optional task identifier.
        session_id: Optional session identifier; auto-generated if missing.

    Returns:
        Configured logger instance.
    """
    if session_id is None:
        session_id = uuid.uuid4().hex[:12]

    log_dir = project_dir / ".orchestrator" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(f"orchestrator.phase.{phase}")
    logger.setLevel(level)
    logger.handlers.clear()
    # Stash project_dir so log_llm_call can persist raw I/O without every
    # call site needing to pass it. Read by log_llm_call via getattr.
    logger._project_dir = project_dir  # type: ignore[attr-defined]

    handler = PhaseFileHandler(log_dir, phase)
    handler.setLevel(level)
    handler.setFormatter(
        JsonFormatter(phase=phase, task_id=task_id, session_id=session_id)
    )
    logger.addHandler(handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(console_handler)

    return logger


def log_llm_call(
    logger: logging.Logger,
    *,
    phase: str,
    role: str,
    messages: list[dict],
    response: Any,
    latency_ms: float,
    endpoint: str | None = None,
    request_id: str | None = None,
) -> None:
    """Log an LLM call with token counts and latency.

    Also persists the full prompt/response round-trip to
    ``.orchestrator/logs/raw-io.jsonl`` when the logger was built by
    ``setup_phase_logger`` (which stashes ``_project_dir`` on the logger).
    This is the audit trail — the token-count log line is the summary.

    Args:
        logger: The phase logger to write to.
        phase: Phase name.
        role: Role name (e.g. ``"coder"``).
        messages: The messages sent to the model.
        response: An ``LLMResponse`` or similar object with token counts.
        latency_ms: Time taken for the call in milliseconds.
        endpoint: Upstream label (operator-defined endpoint name), optional.
        request_id: Stable id for correlating summary and raw records.
            Auto-generated when omitted.
    """
    prompt_tokens = 0
    completion_tokens = 0
    reasoning_tokens = 0

    if response is not None:
        prompt_tokens = getattr(response, "prompt_tokens", 0) or 0
        completion_tokens = getattr(response, "completion_tokens", 0) or 0
        reasoning_tokens = getattr(response, "reasoning_tokens", 0) or 0

    if request_id is None:
        request_id = uuid.uuid4().hex[:16]

    extra: dict[str, Any] = {
        "event": f"llm_call.{role}",
        "phase": phase,
        "request_id": request_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "latency_ms": round(latency_ms, 1),
    }
    record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "",
        0,
        f"LLM call ({role}): {prompt_tokens}p/{completion_tokens}c/{reasoning_tokens}r tokens, {latency_ms:.0f}ms",
        (),
        None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    logger.handle(record)

    project_dir = getattr(logger, "_project_dir", None)
    if project_dir is not None and response is not None:
        from orchestrator.lib.raw_io import write_round_trip

        write_round_trip(
            project_dir,
            phase=phase,
            role=role,
            request_id=request_id,
            messages=messages,
            response=response,
            latency_ms=latency_ms,
            endpoint=endpoint,
        )


def log_llm_error(
    logger: logging.Logger,
    *,
    phase: str,
    role: str,
    error: Exception,
    latency_ms: float,
) -> None:
    """Log a failed LLM call."""
    extra: dict[str, Any] = {
        "event": f"llm_error.{role}",
        "phase": phase,
        "latency_ms": round(latency_ms, 1),
    }
    record = logger.makeRecord(
        logger.name,
        logging.ERROR,
        "",
        0,
        f"LLM call failed ({role}): {error}",
        (),
        None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    logger.handle(record)
