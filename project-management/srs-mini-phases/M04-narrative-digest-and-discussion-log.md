# M04 — Narrative Digest (DWA) And Discussion Log

## Purpose

Turn raw events into readable story: deterministic digests (DWAs) over recent event windows, plus a durable discussion log capturing operator notes, persona statements, agent summaries, disagreements, and decisions.

## Why this phase exists

Raw events are honest but unreadable. Without a story layer, operators have to scroll tables — the dashboard failure mode. Design doc §Recent Story Layer and §Discussion Log Layer, implementation slices 2 and 3. Keep this phase deterministic — no LLM yet (that's M05).

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §Recent Story Layer, §Discussion Log Layer, Slice 2 & 3
- `M01-event-ledger-foundation.md` (done)
- `M03-project-mythos-and-founding-team.md` (for persona→discussion entries)
- `QUALITY_GATES.md` G1, G2, G5

## Implementation surface

- `orchestrator/lib/discussion.py` (append, emit, projection)
- `orchestrator/lib/narrative.py` (deterministic digest rules)
- `.orchestrator/discussion/log.jsonl`
- `.orchestrator/discussion/highlights.jsonl`
- `.orchestrator/narrative/digests/{digest_id}.json` (+ optional `.md`)
- Frontend `EventEngine` narrative fold
- Frontend story satellite + discussion speech-tail rendering (handoff to M06 for visuals)

## Tasks

- [ ] Define event schemas: `discussion_entry_created`, `discussion_highlight_created`, `narrative_digest_created`. Register.
- [ ] `orchestrator/lib/discussion.py`: append helper, secret-scrub pass, JSONL projection, emit event.
- [ ] Convert operator `map notes` → `discussion_entry_created`.
- [ ] Convert persona synthesis output → one `discussion_entry_created` per meaningful statement.
- [ ] Deterministic digest generator (`narrative.py`) triggered on phase/gate cluster boundaries. Window = last N events since prior digest.
- [ ] Digest payload includes: `window.from/to_event_id`, title, summary, highlights[], risks, open_questions, next_step_hint, source_event_ids, artifact_refs.
- [ ] Validate every highlight cites at least one `event:<id>` or `artifact:<ref>`.
- [ ] Frontend fold: `digests[]`, `latestDigestByAtom`, `discussion[]`, `highlights[]`.
- [ ] Frontend renders latest digest near relevant atom cluster (M06 owns visual polish).
- [ ] Replay: digest/discussion state at event N reflects only events ≤ N.

## Quality gates

- [ ] G1 Event integrity.
- [ ] G2 Replay determinism — deterministic digest rules produce identical output on replay.
- [ ] G5 Source-ref credibility — unsourced highlight fails validation, refused at emit.
- [ ] G8 Security — discussion entries scrubbed before persistence.
- [ ] G10 Handoff — new artifact paths registered in AGENT_ONBOARDING.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_discussion.py tests/test_narrative_digest.py
uv run pytest -q web/frontend/tests/test_narrative_fold.py
# rebuild projection from events and diff against on-disk projection file
python -m orchestrator.lib.discussion --rebuild <project_dir>
diff -u <project_dir>/.orchestrator/discussion/log.jsonl.rebuilt <project_dir>/.orchestrator/discussion/log.jsonl
```

## Done means

- [ ] A fixture run produces ≥1 `narrative_digest_created` and ≥1 `discussion_entry_created`.
- [ ] Every highlight carries a valid source ref.
- [ ] Projection files can be rebuilt from events with zero diff.
- [ ] Frontend shows a latest digest card without any LLM involvement.
- [ ] Replay scrub shows digest/discussion state as of the selected event.

## Known traps

- Emitting a digest mid-phase creates windows that include events from the same phase: define the window as `[last_digest_to_event_id + 1 .. latest_event_id]` and record both endpoints.
- If a new event type is added that should feed digests, update the deterministic rule table here **and** in `narrative.py`; tests must cover both.
- Don't let the digest reference events that don't exist (replay divergence).

## Handoff notes

- M05 upgrades deterministic digests with a narrator agent; its JSON validation must preserve the deterministic fallback.
- M06 is responsible for the Story View lens and visual rules.
