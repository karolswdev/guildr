# M03 — Project Mythos And Founding Team State

## Purpose

Make "what we are building, why, and who is shaping it" a durable, event-backed surface. The PWA's first viewport must orient the operator around goal + founding team before anything else.

## Why this phase exists

Design thesis: every project needs Project Mythos, Recent Story, and Next Move Control simultaneously. Without durable mythos/persona events, the PWA has to scrape flat files to render identity — and persona edits disappear into config. SRS §6 (persona), §9 (Mission Control → Founding team editor).

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §Project Mythos Layer, §Persona Mind Editing slice
- `docs/founding-team-consultation-design.md` (bounded recurring consultation contract for A-8)
- `orchestrator/roles/persona_forum.*` and its artifacts (`FOUNDING_TEAM.json`, `PERSONA_FORUM.md`)
- `orchestrator/roles/architect.py` (consumes stance via prompt)
- `M01-event-ledger-foundation.md` (done)
- `QUALITY_GATES.md` G1, G5

## Implementation surface

- `orchestrator/lib/mythos.py` (typed snapshot, diff, event emit)
- `orchestrator/roles/persona_forum.py` (emit on synthesis)
- `web/backend/routes/control.py` persona synthesize / edit handlers
- `web/frontend/src/engine/EventEngine.ts` mythos fold
- `web/frontend/src/ui/MythosHeader.tsx` + `PersonaMindSheet.tsx`
- Artifacts: `FOUNDING_TEAM.json`, `PERSONA_FORUM.md`, new `.orchestrator/mythos/*.json` if needed

## Tasks

- [ ] Define `project_mythos_updated` and `persona_stance_updated` event schemas. Register in `event_schema.py`.
- [ ] Emit `project_mythos_updated` on project creation (from `qwendea.md` + persona config).
- [ ] Emit `project_mythos_updated` + one `persona_stance_updated` per changed persona on persona synthesis.
- [ ] Backend edit route: operator can edit a persona stance → emit `persona_stance_updated` with before/after, persist into `FOUNDING_TEAM.json`.
- [ ] Emit one `discussion_entry_created` per meaningful persona statement (depends on M04 schema landing; if M04 not done, stub entries behind a feature flag).
- [ ] Frontend fold: `mythos: ProjectMythos | null` on `EngineSnapshot`.
- [ ] Mythos header: compact goal, founding team count, stance/consensus indicator, current run status.
- [ ] Persona bodies near discover/plan cluster (M06 will orbit them semantically).
- [ ] Persona Mind Sheet: identity / stance / concerns / last statements / decisions influenced / stance composer.
- [ ] Speech tails from personas to the decisions/atoms they influenced.
- [ ] Add bounded `PersonaForum.consult(...)` for recurring founding-team pulses.
- [ ] Build a `FoundingTeamConsultation` packet with identity, project memory,
  persona memory, prior decisions, trigger evidence, and queued Hero intents.
- [ ] Emit one sourced `discussion_entry_created` per persona for wired consultation triggers.
- [ ] Emit one sourced convergence `discussion_highlight_created` per consultation.
- [ ] Enforce scope guardrails: consultation can clarify/narrow/defer/add evidence, but any expansion is `operator_decision_required`.
- [ ] Make consultation idempotent per trigger event id.
- [ ] Support bounded Hero invitations through operator intent metadata:
  mission, watch-for list, model/provider, originating intent id, and term.
- [ ] Render Hero contributions as temporary council input, not permanent
  founding-team stance, unless explicitly promoted later.

## Quality gates

- [ ] G1 Event integrity.
- [ ] G5 Source-ref credibility — persona stance change events carry source_refs (the triggering event or artifact).
- [ ] G3 Mobile — mythos header fits iPhone portrait, does not occlude map interaction, skeleton state when mythos missing.
- [ ] G4 No-dashboard — mythos appears as map-integrated bodies, not a side panel tab.
- [ ] G8 Security — persona text scrubbed before emission.
- [ ] Consultation boundedness — one trigger creates at most one persona row per current persona plus one convergence highlight.
- [ ] Context boundedness — consultation prompts include wake-up hash/refs and
  short excerpts, never full raw logs or unbounded discussion history.
- [ ] Scope safety — no consultation directly edits workflow, task scope, or artifacts.
- [ ] Hero containment — invited Heroes have source intent, term limit, and
  telemetry; they cannot override convergence or silently expand scope.

## Evidence commands / checks

```bash
uv run pytest -q tests/test_mythos.py tests/test_persona_forum.py web/backend/tests/test_personas.py
uv run pytest -q web/frontend/tests/test_mythos_header.py web/frontend/tests/test_persona_mind_sheet.py
```

## Done means

- [ ] Opening the PWA on a fresh project shows goal + founding team without reading raw config files.
- [ ] Editing a persona stance from the PWA persists and appears in discussion history.
- [ ] Replay to a past event index shows the mythos as it was at that point.
- [ ] Persona bodies are selectable on the map and orbit the discovery cluster.
- [ ] Load-bearing trigger events create bounded founding-team discussion rows visible in replay.

## Known traps

- Do not read `qwendea.md` from the frontend. Backend synthesizes mythos into events.
- A persona stance edit must not silently also edit workflow config — emit a dedicated event; a later consumer applies it.
- Avoid re-emitting `project_mythos_updated` for no-op diffs; folders should not see phantom updates in replay.
- Do not implement recurring consultation as an unbounded multi-agent debate.
  The first version should be deterministic or one structured model call, with
  prior accepted decisions treated as binding context.
- Do not let personas silently ask for the moon after previously accepting
  scope. Scope expansion requires an explicit operator decision.

## Handoff notes

- M04 will fold persona statements into the discussion log projection.
- M06 consumes mythos to render the Goal Core body and Founding Team cluster.
