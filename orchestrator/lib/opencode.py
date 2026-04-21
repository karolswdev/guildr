"""Drive ``opencode`` as an agent runtime subprocess (H6.2).

One call to :meth:`OpencodeSession.run` =

1. Spawn ``opencode run --format json --dir <project> --model <p>/<m> …``
   with ``OPENCODE_CONFIG`` pointing at the per-project overlay from
   :mod:`orchestrator.lib.opencode_config`.
2. Consume stdout line-by-line as NDJSON; forward each event to an
   optional ``event_sink`` (callback or EventBus-like).
3. On exit, call ``opencode export <sessionID>`` to get the canonical
   session record and parse it into :class:`OpencodeResult`.

Why a subprocess + export instead of linking against opencode's API:
opencode is a Node/Bun program. The engine is synchronous Python. A
one-shot subprocess per role is the minimal contract — it also means
anyone can swap the binary for a test shim by putting ``opencode`` on
``PATH`` (see ``tests/test_opencode_session.py``).

No engine imports here. Pure plumbing. Role glue lives in H6.3.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

EventSink = Callable[[dict[str, Any]], None]


@runtime_checkable
class SessionRunner(Protocol):
    """Minimum surface a role needs to drive one agent session.

    ``OpencodeSession`` is the production implementation; dry-run and
    unit tests substitute a fake that returns a canned
    :class:`OpencodeResult`. Kept narrow (one method) so swapping the
    runtime later — e.g. a library call instead of subprocess — only
    has to satisfy this Protocol.
    """

    def run(self, prompt: str) -> "OpencodeResult": ...


class OpencodeError(RuntimeError):
    """Raised when opencode fails to produce a usable session."""


class OpencodeBinaryMissing(OpencodeError):
    """Raised when the opencode binary is not on PATH.

    The engine's own ``PATH`` is inherited, so this is informative
    rather than a silent ``FileNotFoundError``. Operators see the
    install instructions (npm i -g opencode-ai) instead of a cryptic
    ``[Errno 2]``.
    """


@dataclass(frozen=True)
class OpencodeTokens:
    total: int = 0
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0

    @classmethod
    def from_payload(cls, raw: dict[str, Any] | None) -> "OpencodeTokens":
        if not raw:
            return cls()
        cache = raw.get("cache") or {}
        return cls(
            total=int(raw.get("total", 0) or 0),
            input=int(raw.get("input", 0) or 0),
            output=int(raw.get("output", 0) or 0),
            reasoning=int(raw.get("reasoning", 0) or 0),
            cache_read=int(cache.get("read", 0) or 0),
            cache_write=int(cache.get("write", 0) or 0),
        )

    def __add__(self, other: "OpencodeTokens") -> "OpencodeTokens":
        return OpencodeTokens(
            total=self.total + other.total,
            input=self.input + other.input,
            output=self.output + other.output,
            reasoning=self.reasoning + other.reasoning,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
        )


@dataclass(frozen=True)
class OpencodeToolCall:
    tool: str
    input: dict[str, Any]
    output: str
    status: str  # "completed" / "error" / "running"
    started_ms: int
    ended_ms: int


@dataclass(frozen=True)
class OpencodeMessage:
    role: str  # "user" | "assistant"
    provider: str | None
    model: str | None
    tokens: OpencodeTokens
    cost: float
    text_parts: list[str] = field(default_factory=list)
    tool_calls: list[OpencodeToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class OpencodeResult:
    session_id: str
    exit_code: int
    directory: str
    messages: list[OpencodeMessage]
    total_tokens: OpencodeTokens
    total_cost: float
    summary_additions: int
    summary_deletions: int
    summary_files: int
    raw_export: dict[str, Any]
    raw_events: list[dict[str, Any]]

    @property
    def assistant_text(self) -> str:
        """All assistant text parts concatenated, in order.

        The convenience accessor for roles that just want "what did the
        agent say." Tool calls are separate; use ``tool_calls`` to
        reason about file edits / shell output.
        """
        chunks: list[str] = []
        for msg in self.messages:
            if msg.role == "assistant":
                chunks.extend(msg.text_parts)
        return "".join(chunks)

    @property
    def tool_calls(self) -> list[OpencodeToolCall]:
        calls: list[OpencodeToolCall] = []
        for msg in self.messages:
            calls.extend(msg.tool_calls)
        return calls


def _find_binary(binary: str) -> str:
    resolved = shutil.which(binary)
    if resolved is None:
        raise OpencodeBinaryMissing(
            f"opencode binary '{binary}' not found on PATH. "
            "Install with `npm i -g opencode-ai` (see docs/research/opencode-runtime.md)."
        )
    return resolved


def _parse_tool_part(part: dict[str, Any]) -> OpencodeToolCall | None:
    state = part.get("state") or {}
    time_info = state.get("time") or {}
    return OpencodeToolCall(
        tool=str(part.get("tool", "")),
        input=dict(state.get("input") or {}),
        output=str(state.get("output", "") or ""),
        status=str(state.get("status", "") or ""),
        started_ms=int(time_info.get("start", 0) or 0),
        ended_ms=int(time_info.get("end", 0) or 0),
    )


def _parse_message(raw: dict[str, Any]) -> OpencodeMessage:
    info = raw.get("info") or {}
    model = info.get("model") or {}
    parts_raw = raw.get("parts") or []

    text_parts: list[str] = []
    tool_calls: list[OpencodeToolCall] = []
    for part in parts_raw:
        ptype = part.get("type")
        if ptype == "text":
            text_parts.append(str(part.get("text", "")))
        elif ptype == "tool":
            parsed = _parse_tool_part(part)
            if parsed is not None:
                tool_calls.append(parsed)
        # step-start / step-finish parts are bracketing metadata; they
        # already contributed to token totals via info.tokens.

    return OpencodeMessage(
        role=str(info.get("role", "") or ""),
        provider=model.get("providerID"),
        model=model.get("modelID"),
        tokens=OpencodeTokens.from_payload(info.get("tokens")),
        cost=float(info.get("cost", 0) or 0),
        text_parts=text_parts,
        tool_calls=tool_calls,
    )


def parse_export(export_json: dict[str, Any]) -> tuple[list[OpencodeMessage], OpencodeTokens, float, dict[str, int]]:
    """Parse a full ``opencode export`` payload into typed messages + totals.

    Separated so tests can feed a canned export without spawning a
    subprocess. Returns ``(messages, total_tokens, total_cost, summary)``.
    """
    messages_raw = export_json.get("messages") or []
    messages = [_parse_message(m) for m in messages_raw]
    total_tokens = OpencodeTokens()
    total_cost = 0.0
    for m in messages:
        total_tokens = total_tokens + m.tokens
        total_cost += m.cost
    info = export_json.get("info") or {}
    summary = info.get("summary") or {}
    summary_ints = {
        "additions": int(summary.get("additions", 0) or 0),
        "deletions": int(summary.get("deletions", 0) or 0),
        "files": int(summary.get("files", 0) or 0),
    }
    return messages, total_tokens, total_cost, summary_ints


@dataclass
class OpencodeSession:
    """Configured invocation of ``opencode run`` + ``opencode export``.

    One instance is one role's configuration (provider/model/agent/dir);
    call :meth:`run` per prompt. Stateless across calls — if you need
    multi-turn, pass ``continue_session_id`` (opencode ``--session``).
    """

    project_dir: Path
    config_path: Path
    provider: str
    model: str
    agent: str | None = None
    binary: str = "opencode"
    event_sink: EventSink | None = None
    skip_permissions: bool = True

    def _build_argv(self, prompt: str, *, continue_session_id: str | None) -> list[str]:
        argv = [
            self.binary,
            "run",
            "--format",
            "json",
            "--dir",
            str(self.project_dir),
            "--model",
            f"{self.provider}/{self.model}",
        ]
        if self.agent:
            argv.extend(["--agent", self.agent])
        if continue_session_id:
            argv.extend(["--session", continue_session_id])
        if self.skip_permissions:
            argv.append("--dangerously-skip-permissions")
        argv.append(prompt)
        return argv

    def _spawn_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["OPENCODE_CONFIG"] = str(self.config_path)
        # Silence the auto-update check on every spawn — we pin via
        # package.json and don't want the subprocess phoning home.
        env.setdefault("OPENCODE_DISABLE_AUTOUPDATE", "1")
        return env

    def _stream_events(
        self, stdout: Iterable[str]
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Read NDJSON lines, forward to sink, return events + sessionID."""
        events: list[dict[str, Any]] = []
        session_id: str | None = None
        for line in stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # opencode occasionally prints human text alongside the
                # event stream (version banner, warnings). Skip those
                # lines rather than crash the role.
                logger.debug("opencode non-JSON stdout line: %r", line)
                continue
            events.append(event)
            if session_id is None and isinstance(event, dict):
                session_id = event.get("sessionID") or session_id
            if self.event_sink is not None:
                try:
                    self.event_sink(event)
                except Exception:
                    logger.exception("event_sink raised on opencode event")
        return events, session_id

    def _run_export(self, session_id: str) -> dict[str, Any]:
        argv = [self.binary, "export", session_id]
        proc = subprocess.run(
            argv,
            env=self._spawn_env(),
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise OpencodeError(
                f"opencode export {session_id} failed "
                f"(rc={proc.returncode}): {proc.stderr.strip()}"
            )
        # First line of export is a human banner ("Exporting session: …").
        # The JSON body follows — find its start and parse.
        stdout = proc.stdout
        brace = stdout.find("{")
        if brace < 0:
            raise OpencodeError(
                f"opencode export {session_id} produced no JSON: {stdout!r}"
            )
        try:
            return json.loads(stdout[brace:])
        except json.JSONDecodeError as e:
            raise OpencodeError(
                f"opencode export {session_id} emitted invalid JSON: {e}"
            ) from e

    def run(
        self,
        prompt: str,
        *,
        continue_session_id: str | None = None,
        timeout: float | None = 600.0,
    ) -> OpencodeResult:
        """Spawn opencode, stream events, export the session, return a result.

        Raises :class:`OpencodeBinaryMissing` if the binary is not on
        PATH, :class:`OpencodeError` for any other failure that leaves
        us without a usable session (non-zero run exit without an id,
        export failure, malformed export JSON).

        ``timeout`` bounds the role session (seconds). ``None`` means
        no timeout — callers running attended gated sessions can opt
        out, but every PWA-driven role should set one.
        """
        _find_binary(self.binary)
        argv = self._build_argv(prompt, continue_session_id=continue_session_id)
        logger.info("Starting opencode: %s", " ".join(argv))

        proc = subprocess.Popen(
            argv,
            env=self._spawn_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
        )
        try:
            assert proc.stdout is not None
            events, session_id = self._stream_events(proc.stdout)
            stderr = proc.stderr.read() if proc.stderr is not None else ""
            exit_code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise OpencodeError(
                f"opencode run exceeded timeout of {timeout}s "
                f"(session_id so far: {session_id})"
            )

        if session_id is None:
            raise OpencodeError(
                f"opencode run emitted no sessionID (rc={exit_code}); "
                f"stderr={stderr.strip()!r}"
            )
        if exit_code != 0:
            # We still have a session id — export can probably read it.
            # Surface the failure but let the caller decide whether to
            # inspect the partial export.
            logger.warning(
                "opencode run rc=%s for session %s; stderr=%s",
                exit_code, session_id, stderr.strip(),
            )

        export = self._run_export(session_id)
        messages, total_tokens, total_cost, summary = parse_export(export)
        info = export.get("info") or {}

        return OpencodeResult(
            session_id=session_id,
            exit_code=exit_code,
            directory=str(info.get("directory") or self.project_dir),
            messages=messages,
            total_tokens=total_tokens,
            total_cost=total_cost,
            summary_additions=summary["additions"],
            summary_deletions=summary["deletions"],
            summary_files=summary["files"],
            raw_export=export,
            raw_events=events,
        )
