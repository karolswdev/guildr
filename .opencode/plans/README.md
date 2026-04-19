# AI Orchestrator — Plan Index

A system that drives a full SDLC using Qwen3.6 (via llama.cpp) as the sole
model, fronted by a LAN-only single-user PWA. Each build phase of the
orchestrator itself is implemented by an opencode session running that
same Qwen instance — dogfood from day one.

## How to navigate

**If you are an opencode coder agent building a phase, load these files
into context:**

1. `00-overview.md` — what the system is (~2K tok)
2. `01-conventions.md` — file formats: `qwendea.md`, `sprint-plan.md` (~2K tok)
3. `reference/upstream-contract.md` — how to talk to llama-server (~2K tok)
4. `reference/context-budget.md` — token caps, reasoning-strip policy (~1.5K tok)
5. `phases/phase-N-*.md` — your specific phase (~3-5K tok)

Total grounding: ~10-12K tokens. Well within 131K ctx with generous room
for code, tool definitions, and thinking.

**If you are orchestrator code at runtime**, see
`phases/phase-5-orchestrator.md`.

**If you are auditing security**, see `reference/security.md`.

## Phase order

1. [Foundation](phases/phase-1-foundation.md) — HTTP client, state, config
2. [Ingestion](phases/phase-2-ingestion.md) — `qwendea.md` + quiz (PWA-driven)
3. [Architect](phases/phase-3-architect.md) — self-eval loop
4. [Roles](phases/phase-4-roles.md) — coder, tester, reviewer, deployer
5. [Orchestrator](phases/phase-5-orchestrator.md) — engine, validators, gates
6. [Web PWA](phases/phase-6-web-pwa.md) — FastAPI + PWA + LAN middleware
7. [Polish](phases/phase-7-polish.md) — logging, `/metrics`, docs, dry-run

Each phase has: design, task list, acceptance criteria, Evidence Required.
Don't start phase N before N-1 is green.

## Reference (on-demand loads)

- [`upstream-contract.md`](reference/upstream-contract.md) — llama-server
  API, `reasoning_content` quirk, mid-thinking truncation
- [`context-budget.md`](reference/context-budget.md) — per-call token caps,
  reasoning-strip on refine
- [`error-handling.md`](reference/error-handling.md) — retry strategies
- [`security.md`](reference/security.md) — LAN-only middleware, secrets,
  permission scope

## Project constraints (non-negotiable)

- **Model**: Qwen3.6-35B-A3B (UD-Q5_K_XL) via llama.cpp at
  `http://192.168.1.13:8080` (OpenAI-compatible, single slot `-np 1`).
- **Context**: 131072 tokens. Budget per `reference/context-budget.md`.
- **Delivery**: PWA, **single-user**, **LAN-only** by default, monorepo
  (`web/` subdir).
- **Self-eval judge**: same Qwen instance with an adversarial system
  prompt (not a separate model).
- **Server provisioning**: covered separately in
  `~/dev/llama.cpp/llm-server.md` on the inference host. The orchestrator
  assumes the server is already running.
