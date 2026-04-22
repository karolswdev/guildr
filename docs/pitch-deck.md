# Guildr — Pitch Deck

> A LAN-only PWA that lets one operator hand a project to a Qwen-powered SDLC pipeline and *review, follow, and intervene* as it runs — where the touch surface feels like an incredible game, not a spreadsheet dashboard.

**Status:** post-H6 (opencode-per-role) · 518 tests green · dry-run path proven · live-path battle test pending (Harness 2).

This deck is honest about what exists today and optimistic about what the bones can become. Sections marked **Today** describe code that runs right now; sections marked **Trajectory** describe the short roadmap; sections marked **Aspirational** describe vision commitments that are not yet uniformly delivered and are tracked in `analysis/04-22-2026-FEEDBACK.md`.

---

## 1. The one-liner

> *"I pointed my iPhone at my laptop, wrote three sentences of what I wanted, and watched six LLM personas build, test, review, and ship it — on my couch, on my LAN, with no OpenAI bill."*

That is the product experience. Everything below serves it.

---

## 2. The problem

Two problems compound.

**Problem A — agent frameworks feel like terminals.**
The serious orchestration tools (LangGraph, AutoGen, CrewAI, opencode-core, Claude Code) all surface as logs, tool-call JSON, or a REPL. Powerful, but they treat the human as a log reader. You *watch* your agents; you do not *play* with them. The feedback loop is cognitively expensive and emotionally flat.

**Problem B — cloud-first is a poor fit for local-first hardware.**
A modern Mac with a Qwen3.6-35B-A3B model running under llama-server is a serious inference engine. It fits on a desk. It does not leave the house. It has no per-token bill. But the tooling that would let a curious operator *use* that hardware like a game console — hand it a project, watch it think, nudge it when it drifts — does not yet exist in a polished form.

Guildr attacks both at once: a local-first SDLC pipeline with a touch-first, game-grade UI.

```mermaid
quadrantChart
    title Where Guildr sits
    x-axis "CLI / logs" --> "Touch-first game UI"
    y-axis "Cloud / paid tokens" --> "Local / free tokens"
    quadrant-1 "Guildr"
    quadrant-2 "(open space)"
    quadrant-3 "Claude Code, Aider, Cursor"
    quadrant-4 "ChatGPT Agent, v0"
    "Claude Code": [0.15, 0.2]
    "Cursor": [0.25, 0.25]
    "ChatGPT Agent": [0.35, 0.8]
    "v0 / Bolt": [0.5, 0.85]
    "opencode (raw)": [0.2, 0.55]
    "Guildr": [0.82, 0.82]
```

---

## 3. The vision, stated plainly

Guildr is built around ten load-bearing commitments. The full set lives in `analysis/04-22-2026-FEEDBACK.md` §0.1 — the five that define the product identity are:

1. **Qwen-first, local-first.** PRIMARY (192.168.1.13) + ALIEN (192.168.1.70) llama-server endpoints. 128 KiB context ceiling is a hard wall.
2. **Idle-RPG, not watchdog.** The operator can be at dinner. Gates are opt-in, not the norm.
3. **Three pillars, each must be real.** Follow · Review · Intervene. Cosmetic versions of any of these are a failure.
4. **Memory palace is a first-class citizen.** Every claim a role makes should trace back to the project's long-term brain.
5. **Gamification IS the interface.** Not a skin. Action ring, object lens, narrator dialogue, timeline ribbon, compose dock, map — these *are* the UI.

---

## 4. What is already true today

These are not promises. They are the current, tested state of the repo.

| Capability | Status | Evidence |
|---|---|---|
| End-to-end SDLC dry run (Architect → Coder → Tester → Reviewer → Deployer → Judge) | ✅ Green | `tests/test_integration_dry_run.py`, 518 tests |
| Per-role opencode subprocess (H6 migration done) | ✅ Shipped | `orchestrator/cli/run.py::_build_opencode_session_runners` |
| Event ledger as single source of truth (SSE → frontend fold) | ✅ Shipped | `EventBus` → `BridgingEventBus` → `SimpleEventBus`; `EventEngine::applyFold` |
| Operator intents — queued → applied/ignored terminal | ✅ Shipped (M02B) | `web/backend/routes/intents.py` |
| Narrator sidecar with pre-step / refined / fallback modes | ✅ Shipped | `orchestrator/lib/narrator_sidecar.py` |
| Next-step packet projection with memory provenance | ✅ Shipped (M08) | `orchestrator/lib/next_step.py` |
| Founding-team seeding at project start | ✅ Shipped | `orchestrator/roles/persona_forum.py` |
| Memory palace provenance on usage rows + next-step packet | ✅ Shipped | `opencode_audit._emit_usage`, `build_next_step_packet` |
| LAN-only PWA (iPhone over WiFi → laptop) | ✅ Shipped | `web/backend/app.py` + `web/frontend/` |
| Audit trail (`raw-io.jsonl`, `usage.jsonl`, `events.jsonl`, artifacts) | ✅ Shipped | `orchestrator/lib/opencode_audit.py` |

**Test count trajectory:** 438 → 482 → 518 over the H6 → M02B → M08 waves. Dry-run coverage is the reason we can refactor aggressively.

---

## 5. How it works (architecture)

### 5.1 Physical topology

```mermaid
flowchart LR
    subgraph LAN["Home LAN — no internet required"]
        iPhone["📱 iPhone<br/>(operator)"]
        Mac["💻 Mac<br/>(PWA host + orchestrator)"]
        PRIMARY["🧠 PRIMARY<br/>192.168.1.13<br/>llama-server<br/>Qwen3.6-35B-A3B"]
        ALIEN["🧠 ALIEN<br/>192.168.1.70<br/>llama-server<br/>Qwen3.6-35B-A3B"]

        iPhone -- "WiFi · PWA" --> Mac
        Mac -- "OpenAI-compat<br/>HTTP" --> PRIMARY
        Mac -- "OpenAI-compat<br/>HTTP" --> ALIEN
    end

    style iPhone fill:#41C7C7,color:#000
    style Mac fill:#D9B84D,color:#000
    style PRIMARY fill:#2a2a2a,color:#fff
    style ALIEN fill:#2a2a2a,color:#fff
```

No internet. No cloud. No per-token bill. The operator's phone is the touch surface; the laptop is the brain host; the two llama-server boxes are the inference substrate.

### 5.2 Opencode per role

```mermaid
flowchart TB
    subgraph Engine["Orchestrator engine (one per project)"]
        Phase["Phase scheduler"]
    end

    subgraph Sessions["One opencode subprocess per role"]
        Arch["opencode — Architect"]
        Code["opencode — Coder"]
        Test["opencode — Tester"]
        Review["opencode — Reviewer"]
        Deploy["opencode — Deployer"]
        Judge["opencode — Judge"]
        Narr["opencode — Narrator<br/>(neutral summarizer)"]
    end

    Phase --> Arch
    Phase --> Code
    Phase --> Test
    Phase --> Review
    Phase --> Deploy
    Phase --> Judge
    Phase -. "sidecar triggers" .-> Narr

    Arch -->|"HTTP"| Routing{{"routing table<br/>endpoints.yaml"}}
    Code --> Routing
    Test --> Routing
    Review --> Routing
    Deploy --> Routing
    Judge --> Routing
    Narr --> Routing

    Routing -->|"per-role routing"| PRIMARY["PRIMARY<br/>llama-server"]
    Routing -->|"per-role routing"| ALIEN["ALIEN<br/>llama-server"]
```

**Why this matters:** each role has its own session, its own context, its own audit trail. No shared pool, no context bleed. The routing table lets us send heavy roles (Coder) to PRIMARY and lighter roles (Reviewer, Judge) to ALIEN — role-appropriate models, per-endpoint isolation. This is the H6 win.

### 5.3 Event ledger as truth

```mermaid
flowchart LR
    Engine["Engine<br/>EventBus"] -->|"phase_start<br/>phase_done<br/>role_output"| Bridge["BridgingEventBus"]
    Sidecar["Narrator sidecar"] -->|"narrative_digest_created<br/>next_step_packet_created"| Bridge
    Intents["Intent routes"] -->|"intent_queued<br/>intent_applied"| Bridge
    Forum["Persona forum"] -->|"discussion_entry_created"| Bridge

    Bridge --> SSE["SimpleEventBus<br/>(SSE broadcaster)"]
    Bridge --> JSONL["events.jsonl<br/>(durable ledger)"]

    SSE -->|"text/event-stream"| Frontend["Frontend<br/>EventEngine"]
    JSONL -->|"replay"| Frontend

    Frontend -->|"applyFold()"| GameState["Game state<br/>(overlays, map, HUD)"]

    style GameState fill:#41C7C7,color:#000
```

Every operator-visible action is an event. Replay = scrub through events. If a feature cannot be expressed as ledger events, it does not belong in Guildr.

---

## 6. The three pillars (what a real operator gets)

```mermaid
flowchart TB
    Operator["👤 Operator"]

    subgraph Pillars["Three pillars — each must be real"]
        Follow["👁️ Follow<br/><i>see it live</i>"]
        Review["📜 Review<br/><i>audit what happened</i>"]
        Intervene["✋ Intervene<br/><i>nudge what's next</i>"]
    end

    Operator --> Follow
    Operator --> Review
    Operator --> Intervene

    Follow -->|"SSE events<br/>phase state<br/>token burn<br/>narrator dialogue"| FollowUI["Action ring<br/>Timeline ribbon<br/>Narrator overlay"]

    Review -->|"raw-io.jsonl<br/>usage.jsonl<br/>events.jsonl<br/>artifacts/"| ReviewUI["Object lens<br/>Discussion fold<br/>Cost HUD"]

    Intervene -->|"intent queue<br/>gate approvals<br/>next-step packet"| InterveneUI["Compose dock<br/>Gate cards<br/>Next-Step sheet"]
```

**"Intervene was cosmetic" was true pre-M02B.** It is not true anymore. `POST /api/projects/{id}/intents` lands on an intent that the next phase actually reads via the next-step packet projection. The terminal status (`applied` or `ignored`) is not theater — there is a test for it.

---

## 7. The operator journey

```mermaid
sequenceDiagram
    actor Op as Operator (iPhone)
    participant PWA as PWA (Mac)
    participant Eng as Engine
    participant Forum as Founding team
    participant Roles as SDLC roles
    participant Mem as Memory palace

    Op->>PWA: Tap "New project" · dictate qwendea.md
    PWA->>Eng: create project
    Eng->>Mem: init wake-up.md
    Eng->>Forum: synthesize personas
    Forum-->>PWA: discussion_entry_created ×N
    PWA-->>Op: "Your founding team is here"

    Op->>PWA: Toggle gates OFF · Start
    PWA->>Eng: run()

    loop Each SDLC phase
        Eng->>Roles: dispatch role (opencode)
        Roles->>Mem: read memory_refs
        Roles-->>Eng: artifact
        Eng-->>PWA: phase_start / phase_done
        PWA-->>Op: narrator dialogue · timeline advances
        opt Operator is curious
            Op->>PWA: Tap lens on an artifact
            PWA-->>Op: object lens · provenance
        end
        opt Operator wants to nudge
            Op->>PWA: Compose intent
            PWA->>Eng: POST /intents
            Eng->>Eng: next-step packet refreshed
        end
    end

    Eng-->>PWA: run_complete
    PWA-->>Op: "Judge verdict: green · ship?"
```

No blocking. No coercion. The operator *can* look at every detail. They don't *have* to.

---

## 8. Memory palace — the project's long-term brain

**Status:** partially delivered — tracked as A-9 in the audit.

```mermaid
flowchart LR
    subgraph Palace["Memory palace (per project)"]
        WakeUp["wake-up.md<br/>(curated context)"]
        Hash["wake_up_hash<br/>(content ID)"]
        Refs["memory_refs<br/>(fine-grained citations)"]
    end

    Palace -->|"read before<br/>every role call"| Roles["SDLC roles"]
    Roles -->|"stamp provenance"| Events["Event ledger"]

    Events --> Today["✅ Today:<br/>usage rows<br/>next-step packet"]
    Events --> Gap["❌ Aspirational (A-9):<br/>narrative_digest_created<br/>discussion_entry_created<br/>persona_forum_created"]

    style Today fill:#2e7d32,color:#fff
    style Gap fill:#c62828,color:#fff
```

The palace is load-bearing for a review question a cloud agent cannot answer: *"why did this role think that?"* When every user-facing claim stamps `memory_refs`, the operator can tap a digest highlight and see the exact context snippet that shaped it. That is the Review pillar taken seriously.

---

## 9. Founding team — personas as recurring voices

**Status:** seeded-once today; recurring-voice behavior is aspirational — tracked as A-8.

```mermaid
flowchart TB
    Seed["project_seeded"] -->|"✅ today"| Synth["persona_forum_created<br/>discussion_entry_created ×N"]

    subgraph Future["🎯 Trajectory (A-8)"]
        ArchPlan["architect_plan_drafted"] -.->|"consult()"| Review1["discussion_entry_created<br/>tag: review:plan"]
        ArchRefine["architect_refine_done"] -.->|"consult()"| Review2["discussion_entry_created<br/>tag: review:refine"]
        MicroSplit["micro_task_split"] -.->|"consult()"| Review3["discussion_entry_created<br/>tag: review:micro"]
        GateOpen["gate_opened"] -.->|"consult()"| Adv1["discussion_entry_created<br/>tag: advisory:gate"]
        GateReject["gate_rejected"] -.->|"consult()"| Post1["discussion_entry_created<br/>tag: postmortem:gate"]
        PhaseFail["phase_failed"] -.->|"consult()"| Post2["discussion_entry_created<br/>tag: postmortem:phase"]
    end

    Synth --> Fold["Discussion fold (PWA)"]
    Review1 --> Fold
    Review2 --> Fold
    Adv1 --> Fold
    Post1 --> Fold

    style Fold fill:#41C7C7,color:#000
```

The personas are not set-and-forget NPCs. When we close A-8, they will be recurring voices — critiquing the plan, flagging gate openings, writing post-mortems on phase failures. The operator gets a reviewable record of who said what and when.

---

## 10. The PWA as a game surface

```mermaid
flowchart TB
    subgraph Shell["GameShell — layout + overlay coordination"]
        direction TB
        subgraph Top["Top band"]
            Action["Action ring<br/><i>what can I do right now</i>"]
            Timeline["Timeline ribbon<br/><i>where are we in the run</i>"]
        end

        subgraph Center["Center stage"]
            Map["Spatial map / scene<br/><i>the SDLC as terrain</i>"]
            Lens["Object lens<br/><i>tell me about this thing</i>"]
        end

        subgraph Bottom["Bottom band"]
            Narrator["Narrator dialogue<br/><i>JRPG text box, neutral voice</i>"]
            Compose["Compose dock<br/><i>queue an intent</i>"]
            NextStep["Next-Step sheet<br/><i>what's queued, with provenance</i>"]
        end
    end

    Events["Event ledger<br/>(SSE + replay)"] -->|"EventEngine::applyFold"| Shell

    style Action fill:#D9B84D,color:#000
    style Narrator fill:#D9B84D,color:#000
    style NextStep fill:#41C7C7,color:#000
    style Map fill:#2a2a2a,color:#fff
```

**What makes this a game surface and not a dashboard:**

- **Action ring, not menu bar.** The operator always knows *what they can do now*. Actions are large, tactile, iconographic.
- **Object lens, not modal dialog.** Tap anything on the map — a phase, an artifact, a persona — get its story. No nested settings screens.
- **Narrator dialogue, not log tail.** Typewriter cadence, neutral voice, JRPG aesthetic. Summary, not stream.
- **Compose dock, not "add comment."** Intent composition is a first-class motion, not a buried form.
- **Timeline ribbon, not progress bar.** You can scrub. You can replay. You can see the shape of the run.

**Status:** the vocabulary exists in `web/frontend/src/game/GameShell.ts` (1371 lines — an extraction is tracked as C-1). The polish bar is tracked as D-8.

---

## 11. The honest state of play

Because shipping pitch decks that lie is how projects lose trust, here is the current audit picture straight from `analysis/04-22-2026-FEEDBACK.md`:

```mermaid
pie title "Tier 1 blockers — 10 items, status on 2026-04-22"
    "Open" : 7
    "Downgraded after codex review" : 2
    "Rejected after codex review" : 1
```

- **7 open Tier 1 items.** Mostly cohesion and concurrency — "three emitters one contract" (B-2), doc drift (B-9, B-10), HTTP reaching into persona forum privates (B-6), RunRegistry TOCTOU (B-7), sidecar read-modify-write (B-8), one dead method (B-3).
- **518 tests green.** Baseline is solid. The open blockers are hygiene and hardening, not "does the pipeline work."
- **Harness 2 (live-path battle test) is next.** Dry run is proven; live `llama-server` + gates-on run through the PWA has not been done end-to-end since the opencode migration. That is the next milestone.
- **Memory palace uniformity (A-9) and founding-team cadence (A-8) are the two vision gaps.** Both are scoped, both have trigger matrices, both are tractable.

```mermaid
gantt
    title Near-term trajectory
    dateFormat  YYYY-MM-DD
    axisFormat  %b %d

    section Tier 1 blockers
    Docs + STATUS truth (B-9/B-10)     :done,    d1, 2026-04-22, 3d
    Dead code + cohesion (B-3/B-6/B-2) :active,  d2, after d1, 5d
    Concurrency (B-7/B-8)              :         d3, after d2, 4d

    section Live path
    H2.2 opencode wiring smoke         :         h22, 2026-04-25, 3d
    H2.3 live run against PRIMARY      :         h23, after h22, 2d
    H2.4 multi-endpoint routing        :         h24, after h23, 2d
    H2.5 freeze reference run          :         h25, after h24, 1d

    section Vision closure
    A-8 founding-team cadence          :         a8, 2026-05-05, 7d
    A-9 memory palace uniformity       :         a9, 2026-05-05, 7d
    D-8 PWA design principles doc      :         d8, after a8, 3d
```

---

## 12. Where this goes — the M-series roadmap

The live plan is `project-management/srs-mini-phases/M01–M12`. In aggregate:

| Phase | Theme | Shorthand |
|---|---|---|
| M01 | Baseline hygiene | 500+ tests green, H6 landed |
| M02 / M02B | Intent lifecycle | Intervene pillar made real |
| M04 | Narrative digest | Replay with neutral narration |
| M05 | Discussion log | Founding-team forum seeded |
| M06 | PWA lenses + map | The game surface exists |
| M07 | Narrator sidecar | Pre-step + refined + fallback |
| M08 | Next-step packet | Memory-provenance-carrying intent refresh |
| M09 | *Harness 2 completion* | Live-path verified end-to-end |
| M10 | Cost + capacity signals | Honest per-endpoint token economics |
| M11 | Founding-team cadence | A-8 closed; personas as recurring voices |
| M12 | Gamification polish | D-8 closed; design language becomes a doc + tokens |

Every M-phase has a `done-means` block in its file. Every `done-means` is testable.

---

## 13. What's new here — the wedge

A fair question: why not just use opencode, or Cursor, or ChatGPT Agent, or build a thin wrapper over any of them?

| Alternative | What you lose |
|---|---|
| **opencode (raw)** | No operator surface. You are a log reader. No gates UI, no intent queue, no narrator, no map. |
| **Cursor / Aider / Claude Code** | Cloud-first. Per-token bill. No multi-role SDLC orchestration — it's one model at one keyboard. |
| **ChatGPT Agent / v0** | Cloud-bound. Your code leaves the house. You do not choose the model. |
| **LangGraph + Streamlit** | You can build it, but you'd build it. Months of boilerplate for an experience that still looks like a dashboard. |
| **Build from scratch** | That is what we're doing. The wedge is *touch-grade UI over local inference for full-SDLC orchestration* — nobody has shipped it. |

**The wedge in one sentence:** Guildr is the only tool where a curious operator can hand a project to a full SDLC of local Qwen personas and *play* with the run — not merely watch it — with audit, intervene, and replay all first-class and none of them cosmetic.

---

## 14. The ask

This deck exists so a fresh reader — a collaborator, an evaluator, a future-you with cleared context — can land in the repo and understand what is being built, what is real, what is aspirational, and where to start.

**If you are picking up work:** read `analysis/04-22-2026-FEEDBACK.md` §0 and follow the onboarding runbook there.

**If you are evaluating the vision:** §3 of this deck and §0.1 of the audit are the two vision surfaces. They agree by construction.

**If you want to see the bones run:** `.venv/bin/python -m pytest -q` — 518 tests, dry-run path, green. The most honest demo is the one that passes every time.

---

## 15. Closing

Guildr is not trying to replace cloud agents. It is trying to show that local inference + a serious touch-first surface is its own category — one that respects the operator's time, their network, their bill, and their curiosity. The code is further along than the docs suggested before this audit wave. The vision gaps are scoped, not hand-wavy. The next milestone is proving the live path end-to-end.

We are one Harness-2 run away from being able to say, honestly and without asterisks: *live path verified end-to-end via opencode, with gates on, from the PWA.*

That is the headline we are building toward.

---

*Document opened 2026-04-22. Edits land in `analysis/04-22-2026-FEEDBACK.md` §12 changelog.*
