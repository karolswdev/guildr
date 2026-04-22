"""Tests for narrator sidecar coordination."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from orchestrator.lib.narrator_sidecar import (
    SidecarOutcome,
    build_narrator_refined_packet,
    record_sidecar_trigger,
    run_narrator_sidecar,
    should_run_sidecar,
)
from orchestrator.lib.opencode import OpencodeMessage, OpencodeResult, OpencodeTokens
from orchestrator.lib.state import State


class _Events:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields):
        event = {
            "type": event_type,
            "event_id": fields.pop("event_id", f"evt-{len(self.events) + 1}"),
            "schema_version": 1,
            "ts": "2026-04-22T00:00:00Z",
            **fields,
        }
        self.events.append(event)
        return event


def _result(text: str, *, exit_code: int = 0) -> OpencodeResult:
    message = OpencodeMessage(
        role="assistant",
        provider="fake",
        model="fake",
        tokens=OpencodeTokens(total=2, input=1, output=1),
        cost=0.0,
        text_parts=[text],
        tool_calls=[],
    )
    return OpencodeResult(
        session_id="ses_narrator",
        exit_code=exit_code,
        directory=".",
        messages=[message] if text else [],
        total_tokens=message.tokens,
        total_cost=0.0,
        summary_additions=0,
        summary_deletions=0,
        summary_files=0,
        raw_export={},
        raw_events=[],
    )


@dataclass
class _Runner:
    text: str
    calls: int = 0

    def run(self, prompt: str) -> OpencodeResult:
        self.calls += 1
        return _result(self.text)


def _phase_done(event_id: str = "evt-phase-1") -> dict:
    return {
        "event_id": event_id,
        "type": "phase_done",
        "name": "memory_refresh",
        "artifact_refs": [".orchestrator/memory/wake-up.md"],
    }


def _packet() -> dict:
    return {
        "packet_id": "next_base",
        "step": "persona_forum",
        "title": "Founding Team Forum",
        "role": "persona_forum",
        "objective": "Update the founding-team context.",
        "why_now": "memory_refresh completed.",
        "inputs": [],
        "queued_intents": [],
        "intervention_options": ["interject"],
        "context_preview": ["Next step: persona_forum"],
        "source_refs": ["workflow:persona_forum"],
        "memory_provenance": {"memory_refs": []},
    }


def _valid_narrator_json() -> str:
    return json.dumps({
        "title": "Memory completed",
        "summary": "Memory finished and the founding team context is ready.",
        "highlights": [{"text": "Memory completed.", "source_refs": ["event:evt-phase-1"]}],
        "risks": [],
        "open_questions": [],
        "next_step_hint": "Founding Team Forum",
        "source_event_ids": ["evt-phase-1"],
        "artifact_refs": [],
    })


def test_should_run_sidecar_debounces_phase_once(tmp_path: Path) -> None:
    event = _phase_done()

    assert should_run_sidecar(tmp_path, event, event_count=1).run is True
    record_sidecar_trigger(tmp_path, event, event_count=1, status="completed")

    decision = should_run_sidecar(tmp_path, _phase_done("evt-phase-2"), event_count=2)
    assert decision.run is False
    assert decision.reason == "phase_already_summarized"


def test_record_sidecar_trigger_preserves_concurrent_event_ids(tmp_path: Path) -> None:
    events = [
        {"event_id": f"evt-intent-{index}", "type": "operator_intent"}
        for index in range(40)
    ]

    def record(index_and_event: tuple[int, dict]) -> None:
        index, event = index_and_event
        record_sidecar_trigger(
            tmp_path,
            event,
            event_count=index + 1,
            status="completed",
        )

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(record, enumerate(events)))

    state_path = tmp_path / ".orchestrator" / "narrative" / "sidecar-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))

    assert set(state["processed_event_ids"]) == {
        f"evt-intent-{index}" for index in range(40)
    }
    assert state_path.with_name("sidecar-state.lock").exists()
    assert not list(state_path.parent.glob("sidecar-state.json.*.tmp"))


def test_refined_packet_carries_narrator_context_and_sources() -> None:
    digest = {
        "digest_id": "narrator_1",
        "summary": "Narrator summary.",
        "highlights": [{"text": "A sourced highlight.", "source_refs": ["event:evt-phase-1"]}],
        "source_event_ids": ["evt-phase-1"],
        "artifact_refs": [".orchestrator/narrative/digests/narrator_1.json"],
    }

    refined = build_narrator_refined_packet(_packet(), digest)

    assert refined["refined_by"] == "narrator"
    assert refined["base_packet_id"] == "next_base"
    assert refined["narrative_digest_id"] == "narrator_1"
    assert refined["context_preview"][:2] == ["Narrator summary.", "A sourced highlight."]
    assert "event:evt-phase-1" in refined["source_refs"]
    assert "artifact:.orchestrator/narrative/digests/narrator_1.json" in refined["source_refs"]


def test_run_sidecar_with_runner_emits_digest_and_refined_packet(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    events = _Events()
    runner = _Runner(_valid_narrator_json())

    result = run_narrator_sidecar(
        state,
        events,
        [_phase_done()],
        next_step_packet=_packet(),
        runner=runner,
        project_id="project-1",
    )

    assert result is not None
    assert result.status == "completed"
    assert result.outcome == SidecarOutcome.COMPLETED
    assert runner.calls == 1
    event_types = [event["type"] for event in events.events]
    assert "narrative_digest_created" in event_types
    assert "discussion_entry_created" in event_types
    assert "narrator_sidecar_completed" in event_types
    refined_packets = [
        event for event in events.events
        if event["type"] == "next_step_packet_created" and event["packet"].get("refined_by") == "narrator"
    ]
    assert len(refined_packets) == 1
    assert refined_packets[0]["packet"]["base_packet_id"] == "next_base"


def test_run_sidecar_invalid_output_emits_fallback_without_refined_packet(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    events = _Events()

    result = run_narrator_sidecar(
        state,
        events,
        [_phase_done()],
        next_step_packet=_packet(),
        runner=_Runner("not json"),
        project_id="project-1",
    )

    assert result is not None
    assert result.status == "fallback"
    assert result.outcome == SidecarOutcome.FALLBACK
    event_types = [event["type"] for event in events.events]
    assert "narrator_sidecar_fallback" in event_types
    fallback = next(event for event in events.events if event["type"] == "narrator_sidecar_fallback")
    assert fallback["artifact_refs"][0].startswith(".orchestrator/narrative/diagnostics/")
    assert (tmp_path / fallback["artifact_refs"][0]).exists()
    refined_packets = [
        event for event in events.events
        if event["type"] == "next_step_packet_created" and event["packet"].get("refined_by") == "narrator"
    ]
    assert refined_packets == []


def test_run_sidecar_runner_unavailable_emits_skip_outcome(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    events = _Events()

    result = run_narrator_sidecar(
        state,
        events,
        [_phase_done()],
        next_step_packet=_packet(),
        runner=None,
        project_id="project-1",
    )

    assert result is not None
    assert result.status == "fallback"
    assert result.outcome == SidecarOutcome.RUNNER_UNAVAILABLE
    sidecar_events = [
        event["type"] for event in events.events
        if event["type"].startswith("narrator_sidecar_")
    ]
    assert sidecar_events == ["narrator_sidecar_skipped"]
    skipped = next(event for event in events.events if event["type"] == "narrator_sidecar_skipped")
    assert skipped["reason"] == "narrator_runner_unavailable"


def test_run_sidecar_decision_skip_returns_no_sidecar_event(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    event = _phase_done()
    record_sidecar_trigger(tmp_path, event, event_count=1, status="completed")
    events = _Events()

    result = run_narrator_sidecar(
        state,
        events,
        [event],
        next_step_packet=_packet(),
        runner=_Runner(_valid_narrator_json()),
        project_id="project-1",
    )

    assert result is not None
    assert result.status == "skipped"
    assert result.outcome == SidecarOutcome.SKIPPED
    assert [
        event["type"] for event in events.events
        if event["type"].startswith("narrator_sidecar_")
    ] == []


def test_run_sidecar_unsupported_trigger_is_ignored(tmp_path: Path) -> None:
    state = State(tmp_path)
    events = _Events()

    result = run_narrator_sidecar(
        state,
        events,
        [{"event_id": "evt-noop", "type": "noop"}],
        next_step_packet=_packet(),
        runner=_Runner(_valid_narrator_json()),
        project_id="project-1",
    )

    assert result is None
    assert events.events == []
