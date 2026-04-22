# M05 — Narrator / Scribe Agent

## Purpose

Replace deterministic digest text with a bounded, read-only agent that synthesizes DWAs, discussion highlights, and richer next-step packet language from a compact event/artifact packet.
The model voice should stay neutral and useful: a concise project summarizer, not a JRPG character. Its output must be compact enough for a PWA dialogue surface whose visual treatment borrows from JRPG dialogue boxes: speaker label, paced reveal, replay/skip controls, and source-backed text.

## Why this phase exists

Deterministic digests (M04) are honest but terse. The Narrator/Scribe adds readable synthesis while remaining cheap and auditable — a `SessionRunner` role with no shell, read-only tools, capped context, JSON-validated output. Design doc §Agent Design: Narrator / Scribe + Slice 4.

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §Agent Design: Narrator / Scribe, Slice 4
- `orchestrator/lib/opencode.py` (`SessionRunner` Protocol)
- `orchestrator/lib/opencode_audit.py` (session → raw-io/usage)
- `orchestrator/roles/reviewer.py` (reference: opencode session SDLC role)
- `M04-narrative-digest-and-discussion-log.md` (done — deterministic fallback must remain)
- `QUALITY_GATES.md` G1, G5, G7, G8

## Implementation surface

- `orchestrator/roles/narrator.py`
- `orchestrator/roles/narrator_dryrun.py` (DryRunNarratorRunner)
- `orchestrator/roles/prompts/narrator/generate.txt`
- `orchestrator/lib/narrator_sidecar.py`
- `orchestrator/lib/opencode_config.py` (agent allowlist: read/grep only, no shell/write)
- Engine wiring: narrator as workflow phase OR engine sidecar hook after major steps
- Frontend narrator presentation: JRPG-style visual dialogue layer over `GameShell`, without requiring a JRPG persona prompt
- Artifacts: `.orchestrator/narrative/digests/*.json` and `.md`

## Tasks

- [x] Add `agent.narrator` definition with tools `{read, grep}` only; shell/write/edit disabled.
- [x] Construct bounded input packet: project goal, workflow snapshot, last N events, recent artifact excerpts, pending discussion, next step.
- [x] Narrator prompt contract: JSON only, fields per design-doc output contract.
- [x] JSON validator: all `source_event_ids` exist in packet, all `artifact_refs` are safe relative paths, summary length cap, no secrets.
- [x] Debounce: at most once per phase, at most once per 10 events unless gate/error/intent event intervenes.
- [x] Trigger points: after `phase_done`, `gate_decided`, `phase_error`, and `operator_intent`.
- [x] Trigger point: before a step if no recent packet exists.
- [x] Emit `narrative_digest_created` and one `discussion_entry_created` per valid narrator pass.
- [x] Emit a narrator-refined `next_step_packet_created` per narrator pass.
- [x] Audit via `emit_session_audit` (raw-io + usage rows, shared `call_id`).
- [x] On validation failure, keep the deterministic M04 digest — do not corrupt the ledger.
- [x] DryRun runner returns canned deterministic output so focused pipeline tests can use the opencode role without a binary.
- [x] Live/config path routes `narrator` through opencode with the read-only agent definition.
- [x] PWA renders latest narrator/DWA text through a game-grade dialogue layer, not a generic card or roleplay persona.
- [x] Dialogue presentation supports typewriter reveal, skip, replay, reduced-motion fallback, and source affordance.
- [x] Expose narrator as an engine-side post-phase hook.
- [x] Expose narrator as an optional workflow phase configured in workflow.

## Quality gates

- [x] G1 Event integrity on narrator emissions.
- [x] G5 Source-ref credibility — narrator output fails validation if unsourced.
- [x] G7 Cost truth — every narrator session emits `usage_recorded` with `provider_kind=opencode`.
- [x] G8 Security — read-only tools; no write/shell; scrub outputs before emit.
- [x] G3/G4 PWA presentation — narrator output feels like in-world narration and does not regress into dashboard cards.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_narrator.py tests/test_integration_narrator_pipeline.py
uv run pytest -q tests/test_narrator_sidecar.py tests/test_engine.py::TestLoopEvents web/backend/tests/test_intents.py
uv run pytest -q tests/test_narrator.py tests/test_narrator_sidecar.py tests/test_engine.py::TestLoopEvents orchestrator/tests/test_workflow.py
uv run pytest -q tests/test_opencode_audit.py  # regression for shared call_id
uv run pytest -q tests/test_opencode_config.py::test_narrator_agent_is_read_only
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py
./web/frontend/build.sh
# dry-run pipeline emits exactly one digest + one next-step packet
```

## Done means

- [x] Dry-run narrator runner produces one valid DWA JSON payload.
- [x] Dry-run run produces one next-step packet from the narrator role.
- [x] Live/config path routes `narrator` through opencode with agent definition.
- [x] Audit rows exist for each narrator session (raw-io.jsonl + usage.jsonl joined on call_id).
- [x] Invalid narrator JSON falls back without corrupting the ledger; deterministic digest remains.
- [x] No secrets in narrator packet/output artifacts covered by focused tests.

## Known traps

- Narrator writing to project files is a silent regression — enforce tool allowlist and a test that fails if write/edit/bash appear in the agent definition.
- Passing the full ledger as input defeats the purpose. Packet must be bounded (N events, truncated artifact excerpts).
- Debounce must not be defeated by rapid operator intents; separate counter for intents vs other events.
- A narrator digest rendered as a plain administrative panel is a product regression. Default presentation should be a dialogue UI over the map, with story cards as the expandable detail view; the model prompt itself stays neutral and summarizer-oriented.

## Handoff notes

- M06 should deepen the narrator dialogue surface with story cards, satellites, and source previews.
- If the narrator becomes the primary next-step generator, M02's deterministic generator stays as fallback.
