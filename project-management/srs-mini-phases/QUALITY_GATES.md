# Cross-Phase Quality Gates

These gates apply across mini-phases. They catch regressions a single phase's local tests cannot see. A mini-phase is not done until the applicable gates here are green.

## G1. Event integrity

- [ ] Every new event type writes `event_id` (ULID), `schema_version` (int), `ts` (ISO8601), `type`, `run_id`.
- [ ] `event_id`s are unique within a run; SSE dedup works off them, not `ts`.
- [ ] Unknown `schema_version` values cause readers to refuse, not silently misparse.
- [ ] Every live SSE event also persists to `.orchestrator/events.jsonl` in the same record.
- [ ] Event payloads reference artifacts by stable relative path, never by absolute path.

## G2. Replay determinism

- [ ] Folded snapshot at event-index N is a pure function of events [0..N]. No wall-clock, no random.
- [ ] Replay of a durable run reproduces the same narrative, cost, and loop snapshots that live run produced.
- [ ] Replay does NOT restore filesystem state — test must assert no project file was touched during replay.
- [ ] Narrative digests shown at replay point = digests known at that point (not recomputed from current workflow).
- [ ] Next-step packet in replay mode = packet known at that point.

## G3. Mobile usability

- [ ] First viewport on iPhone portrait answers: what, who, what just happened, what is next, where to intervene.
- [ ] No HUD, label, or preview overlaps at 375×812.
- [ ] Touch targets ≥ 44×44 points.
- [ ] No reliance on hover for essential info.
- [ ] Story/narrative lens legible without horizontal scroll.

## G4. No-dashboard-regression

- [ ] No new tab/table/card grid introduced as primary surface.
- [ ] Every visible object has semantic, orientation, or interaction value.
- [ ] Loops read as gravitational clusters, not a Kanban.
- [ ] DIRECTION_GUARDRAILS quality questions each answerable without scrolling a table.

## G5. Source-ref credibility

- [ ] Every narrative digest highlight carries at least one `event:<id>` or `artifact:<ref>`.
- [ ] Every persona stance change carries the triggering event/ artifact id.
- [ ] UI refuses to render an unsourced narrative claim (or clearly marks it `inferred`).
- [ ] `source_refs` paths are path-safe and validated against project root.

## G6. Intent lifecycle

- [ ] Every submitted `operator_intent` gets exactly one terminal outcome event: `operator_intent_applied` or `operator_intent_ignored`.
- [ ] `client_intent_id` is assigned by the PWA and round-trips through all outcome events.
- [ ] `queued → applied/ignored/superseded` state transitions are visible on the map.
- [ ] An applied intent references the artifact/prompt it was injected into.

## G7. Cost truth

- [ ] Every LLM / advisor / retry / escalation / session-assistant-message emits one `usage_recorded`.
- [ ] `cost.source ∈ {provider_reported, rate_card_estimate, local_estimate, unknown}`.
- [ ] Budget state present with explicit `null` when unset, never missing.
- [ ] Historical replay uses snapshotted rate cards, not today's pricing.
- [ ] `rollup()` joins raw-io.jsonl ↔ usage.jsonl with zero orphans.

## G8. Security / scrubbing

- [ ] No secrets in events, artifacts, prompts, logs, or PWA state.
- [ ] Advisor API keys only via env / secure local config. Never in `events.jsonl`.
- [ ] `orchestrator/lib/scrub.py` is the single scrub implementation.
- [ ] Project path traversal blocked: every file ref validated against project root.
- [ ] LAN-only by default; `ORCHESTRATOR_EXPOSE_PUBLIC=1` is a conscious opt-in.

## G9. Accessibility and fallback

- [ ] All map actions have a keyboard/DOM fallback.
- [ ] ARIA labels on every interactive SVG/canvas overlay control.
- [ ] Motion-reduce respected: `prefers-reduced-motion` disables non-essential animation.
- [ ] Text overlays never precisely depend on color alone to convey state.
- [ ] When WebGL fails to init, a usable DOM surface appears without a page reload.

## G10. Handoff quality

- [ ] `../STATUS.md` Evidence Log updated with exact commands + pass counts.
- [ ] Phase file footer carries `Completed YYYY-MM-DD by <agent>`.
- [ ] New primitives/artifact paths/event types added to `../AGENT_ONBOARDING.md` glossary.
- [ ] New traps added to the phase file and to AGENT_ONBOARDING traps list if cross-phase.
- [ ] `git diff --check` clean.
- [ ] No commits were created without user approval.
