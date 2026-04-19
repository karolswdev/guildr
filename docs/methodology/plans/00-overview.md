# AI Orchestrator — Overview

## What this is

A system that takes a one-file project description (`qwendea.md`) and
drives it through a full SDLC — planning, architecture, implementation,
testing, review, deployment — using a single Qwen3.6-35B-A3B instance as
every agent role, with human approval gates at key transitions.

## Why

Frontier-model SDLC automation is well-covered. This project targets a
**local, single-user, LAN-only** setup where the same Qwen instance plays
every role, controls are tight, and the whole thing can be kicked off
from a phone over Wi-Fi.

## Layered architecture

```
┌──────────────────────────────────────────────────────────────┐
│  PWA (phone/desktop browser)                                 │
│  — new project, review plan, approve gates, watch progress   │
└──────────────────┬───────────────────────────────────────────┘
                   │ HTTP/SSE (LAN-only middleware)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI — orchestrator control plane                        │
│  — project lifecycle, gate approvals, progress stream        │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Orchestrator engine (Python)                                │
│  — phase state machine, retries, validators, session queue   │
│                                                               │
│  Roles: Architect → Coder → Tester → Reviewer → Deployer     │
└──────────────────┬───────────────────────────────────────────┘
                   │ OpenAI protocol
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  llama-server (llama.cpp) @ 192.168.1.13:8080                │
│  — Qwen3.6-35B-A3B UD-Q5_K_XL, 131K ctx, -np 1               │
└──────────────────────────────────────────────────────────────┘
```

## Data flow

1. User opens PWA → `POST /projects` with a project idea.
2. If `qwendea.md` missing: PWA runs interactive quiz (3-10 turns,
   **native PWA UI**, not through llama-server). Quiz synthesis is
   the only LLM call in this phase.
3. Orchestrator runs the Architect with a self-evaluation loop
   (see `phases/phase-3-architect.md`). Output: `sprint-plan.md`.
4. **Human gate 1**: PWA shows sprint-plan; user approves or rejects.
5. Coder works through sprint-plan tasks sequentially (parallelism
   constrained by `-np 1`; see `reference/upstream-contract.md`).
6. Tester re-runs Evidence Required commands per task.
7. Reviewer compares implementation to sprint-plan.
8. **Human gate 2**: review approval.
9. Deployer prepares deployment artifacts.

## Key invariants

- **Single source of truth per phase**: `qwendea.md` → `sprint-plan.md`
  → code + Evidence Logs → `TEST_REPORT.md` → `REVIEW.md` →
  `DEPLOY.md`. Never bypass.
- **Evidence is the proof**: the Coder's self-reported "done" does not
  count until the Tester re-runs Evidence Required commands.
- **The same Qwen plays every role** via different system prompts. The
  self-eval "judge" is adversarially prompted (see phase 3) to offset
  same-model bias.
- **LAN-only by default**: PWA backend enforces RFC1918 source IPs.
- **Context budget is a first-class concern** — see
  `reference/context-budget.md`.

## What each phase produces

| Phase       | Input                    | Output                          |
|-------------|--------------------------|---------------------------------|
| Ingestion   | User answers / text      | `qwendea.md`                    |
| Architect   | `qwendea.md`             | `sprint-plan.md`                |
| Coder       | Task slice               | Source files + Evidence Log     |
| Tester      | `sprint-plan.md` + code  | `TEST_REPORT.md`                |
| Reviewer    | Everything above         | `REVIEW.md`                     |
| Deployer    | `REVIEW.md` + code       | `DEPLOY.md` + scripts           |

## Out of scope for this plan

- Standing up the llama.cpp server. See `~/dev/llama.cpp/llm-server.md`.
- Multi-user auth; remote-over-internet access.
- Parallelism beyond the single `-np 1` server slot. See
  `phases/phase-7-polish.md` for the queue design.
