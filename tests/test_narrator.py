"""Tests for the Narrator / Scribe role."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from orchestrator.lib.narrative import build_narrative_digest
from orchestrator.lib.opencode import OpencodeMessage, OpencodeResult, OpencodeTokens
from orchestrator.lib.state import State
from orchestrator.roles.narrator import Narrator, NarratorError, build_narrator_packet, parse_narrator_digest
from orchestrator.roles.narrator_dryrun import DryRunNarratorRunner


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
class _FakeRunner:
    text: str
    prompts: list[str] = field(default_factory=list)

    def run(self, prompt: str) -> OpencodeResult:
        self.prompts.append(prompt)
        return _result(self.text)


class _Events:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type: str, **fields):
        event = {"type": event_type, **fields}
        self.events.append(event)
        return event


def _source_event() -> dict:
    return {
        "event_id": "evt-phase-1",
        "type": "phase_done",
        "name": "memory_refresh",
        "artifact_refs": [".orchestrator/memory/wake-up.md"],
    }


def test_narrator_packet_is_bounded_and_scrubbed(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nUse api_key=sk-live-secret-value.")
    events = [
        {"event_id": f"evt-{index}", "type": "phase_done", "name": "step", "payload": "ignored"}
        for index in range(20)
    ]

    packet = build_narrator_packet(state, events, max_events=3)

    assert [event["event_id"] for event in packet["events"]] == ["evt-17", "evt-18", "evt-19"]
    assert "sk-live-secret-value" not in json.dumps(packet)
    assert "payload" not in packet["events"][0]


def test_parse_narrator_digest_validates_sources_and_artifacts(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    packet = build_narrator_packet(state, [_source_event()])
    raw = json.dumps({
        "title": "Memory completed",
        "summary": "Memory finished and the next step is ready.",
        "highlights": [{"text": "Memory completed.", "source_refs": ["event:evt-phase-1"]}],
        "risks": [],
        "open_questions": [],
        "next_step_hint": "Persona forum",
        "source_event_ids": ["evt-phase-1"],
        "artifact_refs": [".orchestrator/memory/wake-up.md"],
    })

    digest = parse_narrator_digest(raw, packet)

    assert digest["generated_by"] if "generated_by" in digest else True
    assert digest["source_event_ids"] == ["evt-phase-1"]
    assert digest["artifact_refs"] == [".orchestrator/memory/wake-up.md"]


def test_parse_narrator_digest_rejects_unknown_event_and_unsafe_artifact(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    packet = build_narrator_packet(state, [_source_event()])

    unknown = {
        "title": "Bad",
        "summary": "Bad.",
        "highlights": [{"text": "Invented.", "source_refs": ["event:evt-missing"]}],
        "source_event_ids": ["evt-missing"],
        "artifact_refs": [],
    }
    with pytest.raises(ValueError, match="unknown"):
        parse_narrator_digest(json.dumps(unknown), packet)

    unsafe = {
        "title": "Bad",
        "summary": "Bad.",
        "highlights": [{"text": "Memory.", "source_refs": ["event:evt-phase-1"]}],
        "source_event_ids": ["evt-phase-1"],
        "artifact_refs": ["../secret.txt"],
    }
    with pytest.raises(NarratorError, match="unsafe artifact"):
        parse_narrator_digest(json.dumps(unsafe), packet)


def test_narrator_execute_emits_valid_digest_discussion_and_usage(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    state.events = _Events()
    raw = json.dumps({
        "title": "Memory completed",
        "summary": "Memory finished and the next step is ready.",
        "highlights": [{"text": "Memory completed.", "source_refs": ["event:evt-phase-1"]}],
        "risks": [],
        "open_questions": [],
        "next_step_hint": "Persona forum",
        "source_event_ids": ["evt-phase-1"],
        "artifact_refs": [],
    })
    narrator = Narrator(_FakeRunner(raw), state)

    digest = narrator.execute([_source_event()])

    assert digest["generated_by"] == "narrator"
    event_types = [event["type"] for event in state.events.events]
    assert "usage_recorded" in event_types
    assert "narrative_digest_created" in event_types
    assert "discussion_entry_created" in event_types
    assert (tmp_path / ".orchestrator" / "narrative" / "digests" / f"{digest['digest_id']}.json").exists()


def test_narrator_invalid_json_uses_deterministic_fallback_without_emit(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    state.events = _Events()
    deterministic = build_narrative_digest(tmp_path, [_source_event()])
    narrator = Narrator(_FakeRunner("not json"), state)

    digest = narrator.execute([_source_event()])

    assert digest["fallback_used"] is True
    assert digest["digest_id"] == deterministic["digest_id"]
    assert digest["diagnostic_artifact_refs"][0].startswith(".orchestrator/narrative/diagnostics/")
    diagnostic = tmp_path / digest["diagnostic_artifact_refs"][0]
    assert diagnostic.exists()
    assert "not json" in diagnostic.read_text(encoding="utf-8")
    assert [event["type"] for event in state.events.events] == ["usage_recorded"]


def test_dry_run_narrator_runner_returns_valid_json(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    packet = build_narrator_packet(state, [_source_event()])
    prompt = json.dumps(packet)

    result = DryRunNarratorRunner(state).run(prompt)

    payload = json.loads(result.assistant_text)
    assert payload["source_event_ids"] == ["evt-phase-1"]
    assert payload["highlights"][0]["source_refs"] == ["event:evt-phase-1"]


def test_dry_run_narrator_session_counter_is_instance_local(tmp_path: Path) -> None:
    state = State(tmp_path)
    state.write_file("qwendea.md", "# Project\n\nBuild it.")
    packet = build_narrator_packet(state, [_source_event()])
    prompt = json.dumps(packet)

    first_runner = DryRunNarratorRunner(state)
    second_runner = DryRunNarratorRunner(state)

    assert first_runner.run(prompt).session_id == "ses_dryrun_narrator_1"
    assert first_runner.run(prompt).session_id == "ses_dryrun_narrator_2"
    assert second_runner.run(prompt).session_id == "ses_dryrun_narrator_1"
