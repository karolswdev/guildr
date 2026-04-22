# Traceability Matrix

Maps SRS sections and design-doc slices to mini-phases. Use this when:

- triaging a bug to the right phase,
- confirming a SRS requirement is owned somewhere,
- planning cross-cutting work without duplicating it.

## SRS sections → mini-phases

| SRS § | Topic | Primary mini-phase | Touches |
| --- | --- | --- | --- |
| 4.1–4.2 | Memory mandatory, context budgeted | M08 | M01, M05 |
| 4.3–4.4 | Atomic work, explicit goals | M02, M04 | M06 |
| 4.5 | Events durable | M01 | all |
| 4.6 | User can intervene | M02 | M06, M10 |
| 4.7 | Agents replaceable | M09 | M11 |
| 4.8 | UI shows causality | M04, M06, M07 | M02, M03 |
| 4.9 | Cost is visible state | M09 | M01 |
| 4.10 | Batteries provided, boundaries programmable | M09, M10 | — |
| 6.1 | Memory Spine (MemPalace) | M08 | M05 |
| 6.2 | Atomic Workflow Model | M02, M10 | M06 |
| 6.3 | Architect Requirements | already H6.3e | M02 (task packets) |
| 6.4 | Phase Files | M02 | — |
| 6.5 | Guru Escalation | M10, M09 | M05 |
| 7 | Hookability | M10 | M09, M11 |
| 8 | Event Ledger And Replay | M01 | M06, M11 |
| 8.1 | Cost Ledger / Budget Replay | M09 | M01 |
| 8.2 | SDLC Loop Replay | M11 | M01, M06 |
| 9 | PWA Requirements (Core screens, Mission Control) | M06 | M02–M05, M07 |
| 10 | Agent Coordination | M02, M04 | M08 |
| 11 | Model Provider Requirements | M09 | M10 |
| 12 | Data And Artifacts | M07 | M01, M08 |
| 13 | Nonfunctional (perf, reliability, security, portability, observability) | M12 | all |
| 14 M1 | Memory + Replay Foundation | M01, M08 | — |
| 14 M2 | Atomic Coordination | M02 | M10 |
| 14 M3 | Replay Viewer | M06, M11 | M07, M09 |
| 14 M4 | Provider And Guru Mesh | M09, M10 | M11 |
| 14 M5 | Game-Like PWA Surface | M06 | M03–M07 |
| 15 | Acceptance Criteria | M12 | all |
| 17 | Current Implementation Status | gated by `../STATUS.md` | — |
| 18 | Three.js Client Design Documents | M06 | M03, M04, M07 |

## `docs/pwa-narrative-replay-and-intervention-design.md` → mini-phases

| Design section | Mini-phase |
| --- | --- |
| Product Thesis (three simultaneous views) | M03 + M04 + M02 |
| Information Architecture §1 Project Mythos | M03 |
| Information Architecture §2 Recent Story (DWA) | M04 |
| Information Architecture §3 Next-Step Control | M02 |
| Information Architecture §4 Discussion Log | M04 |
| Default PWA Screen (Global/Object/Story View) | M06 |
| Event Architecture (new event types, folding rules, replay) | M01 (baseline) + owning phase per type |
| Narrator / Scribe Agent | M05 |
| Backend Work Items B1–B6 | B1→M01, B2→M04, B3→M05, B4→M02, B5→M02, B6→M03 |
| Frontend Work Items F1–F8 | F1→M01, F2–F3→M03+M06, F4→M04+M06, F5→M02+M06, F6→M02+M06, F7→M06+M11, F8→M07 |
| Visual Grammar (Goal Core, Founding Team, DWA, Next-Step Beam, Intent Packet) | M06 with inputs from M02–M04 |
| Implementation Slice 1 — Deterministic Next-Step Sheet | M02 + M06 |
| Implementation Slice 2 — Discussion Log Events | M04 |
| Implementation Slice 3 — Deterministic DWA digest | M04 |
| Implementation Slice 4 — Narrator Agent | M05 |
| Implementation Slice 5 — Intent Outcomes | M02 |
| Implementation Slice 6 — Persona Mind Editing | M03 |
| Acceptance Criteria For The Whole Layer | M12 |

## Other design docs

| Doc | Primary mini-phase |
| --- | --- |
| `docs/cost-tracking.md` | M09 |
| `docs/sdlc-loop-visualization.md` | M11 (loop replay); M06 (lens) |
| `docs/ux-interaction-model.md` | M06 |
| `docs/spatial-flow-universe-design.md` | M06 |
| `docs/threejs-asset-pipeline.md` | M06 + M12 |
| `docs/design-review-protocol.md` | M12 |
| `docs/implementation-roadmap.md` | M12 (release gating) |

## Reverse index: find the mini-phase that owns a term

- `event_id` / `schema_version` / `events.jsonl` → M01
- `operator_intent*`, `next_step_packet_created`, Nudge/Intercept/Shape → M02
- `project_mythos_updated`, `persona_stance_updated`, FOUNDING_TEAM.json → M03
- `narrative_digest_created`, `discussion_entry_created`, DWA → M04
- Narrator role, `.orchestrator/narrative/digests/` → M05
- Goal Core, Object View, Story View, Next-Step Beam, Mission Control lens → M06
- `artifact_preview_created`, artifact route previews → M07
- `memory_refresh`, `wake-up.md`, MemPalace wings → M08
- `usage_recorded`, budget gates, provider health, rate-card snapshot → M09
- Hook points, workflow config, guru escalation, OpenRouter/CLI advisors → M10
- Live-path resilience, SSE reconnect, `loop_*` events, SDLC loop replay → M11
- Acceptance Criteria, release gates, perf budget, security review → M12
