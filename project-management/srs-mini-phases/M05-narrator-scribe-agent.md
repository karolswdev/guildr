# M05 — Narrator / Scribe Agent

## Purpose

Replace deterministic digest text with a bounded, read-only agent that synthesizes DWAs, discussion highlights, and richer next-step packet language from a compact event/artifact packet.

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
- `orchestrator/lib/opencode_config.py` (agent allowlist: read/grep only, no shell/write)
- Engine wiring: narrator as workflow phase OR engine sidecar hook after major steps
- Artifacts: `.orchestrator/narrative/digests/*.json` and `.md`

## Tasks

- [ ] Add `agent.narrator` definition with tools `{read, grep}` only; shell/write/edit disabled.
- [ ] Construct bounded input packet: project goal, workflow snapshot, last N events, recent artifact excerpts, open gates, pending intents, next step.
- [ ] Narrator prompt contract: JSON only, fields per design-doc output contract.
- [ ] JSON validator: all `source_event_ids` exist in packet, all `artifact_refs` are safe relative paths, summary length cap, no secrets.
- [ ] Debounce: at most once per phase, at most once per 10 events unless gate/error/intent event intervenes.
- [ ] Trigger points: after `phase_done`, `gate_decided`, `phase_error`, `operator_intent`, and before a step if no recent packet exists.
- [ ] Emit `narrative_digest_created`, zero or more `discussion_entry_created`, and a `next_step_packet_created` per narrator pass.
- [ ] Audit via `emit_session_audit` (raw-io + usage rows, shared `call_id`).
- [ ] On validation failure, keep the deterministic M04 digest — do not corrupt the ledger.
- [ ] DryRun runner returns canned deterministic output so full pipeline tests keep passing.
- [ ] Expose narrator as an optional workflow phase AND an engine-side post-phase hook (see Open Question in design doc; support both, configured in workflow).

## Quality gates

- [ ] G1 Event integrity on narrator emissions.
- [ ] G5 Source-ref credibility — narrator output fails validation if unsourced.
- [ ] G7 Cost truth — every narrator session emits `usage_recorded` with `provider_kind=opencode`.
- [ ] G8 Security — read-only tools; no write/shell; scrub outputs before emit.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_narrator.py tests/test_integration_narrator_pipeline.py
uv run pytest -q tests/test_opencode_audit.py  # regression for shared call_id
# dry-run pipeline emits exactly one digest + one next-step packet
```

## Done means

- [ ] Dry-run run produces one DWA and one next-step packet from the narrator role.
- [ ] Live/config path routes `narrator` through opencode with agent definition.
- [ ] Audit rows exist for each narrator session (raw-io.jsonl + usage.jsonl joined on call_id).
- [ ] Invalid narrator JSON fails loudly; deterministic digest remains.
- [ ] No secrets in any narrator artifact.

## Known traps

- Narrator writing to project files is a silent regression — enforce tool allowlist and a test that fails if write/edit/bash appear in the agent definition.
- Passing the full ledger as input defeats the purpose. Packet must be bounded (N events, truncated artifact excerpts).
- Debounce must not be defeated by rapid operator intents; separate counter for intents vs other events.

## Handoff notes

- M06 may render narrator-authored `why_now`/`context_preview` in the Next-Step Sheet.
- If the narrator becomes the primary next-step generator, M02's deterministic generator stays as fallback.
