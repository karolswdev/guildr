# Architecture

This document summarizes the orchestrator system design. For detailed
phase specifications, see the individual phase files in `phases/`.

## System layers

```
┌──────────────────────────────────────────────────────────────┐
│  PWA (vanilla TS, hash routing, Service Worker)              │
│  Views: NewProject, Quiz, Progress, Gate, Artifacts          │
└──────────────────┬───────────────────────────────────────────┘
                   │ HTTP / SSE (LAN-only, RFC1918 enforcement)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI backend                                             │
│  Routes: projects, quiz, gates, stream, metrics, artifacts   │
│  Middleware: LanOnlyMiddleware (RFC1918 source check)         │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  Orchestrator engine                                         │
│  Phase state machine with retries, validators, gates         │
│  Roles: Architect → Coder → Tester → Reviewer → Deployer    │
└──────────────────┬───────────────────────────────────────────┘
                   │ OpenAI protocol (chat completions)
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  llama.cpp server pool                                       │
│  PRIMARY:  192.168.1.13:8080 (Q5 quant)                     │
│  ALIEN:    192.168.1.70:8080 (Q6 quant)                     │
│  Same model, different quant — role-based routing            │
└──────────────────────────────────────────────────────────────┘
```

## Key modules

### `orchestrator/engine.py`

The phase state machine. `Orchestrator.run()` executes phases in order:

```
architect → gate → implementation → testing → review → gate → deployment
```

Each phase is retried up to `config.max_retries` on validator failure.
Raises `PhaseFailure` when all retries are exhausted.

### `orchestrator/roles/`

Each role is a class that inherits from `BaseRole`:

| Module | Class | Responsibility |
|---|---|---|
| `architect.py` | `Architect` | Produces `sprint-plan.md` from `qwendea.md` with self-eval loop |
| `coder.py` | `Coder` | Implements sprint-plan tasks sequentially |
| `tester.py` | `Tester` | Re-verifies Coder's Evidence Log entries |
| `reviewer.py` | `Reviewer` | Compares implementation against sprint plan |
| `deployer.py` | `Deployer` | Produces `DEPLOY.md` with deployment plan |

### `orchestrator/lib/`

| Module | Purpose |
|---|---|
| `llm.py` | `LLMClient` — wraps OpenAI SDK for llama-server |
| `llm_fake.py` | `FakeLLMClient` — dry-run mode, canned responses |
| `pool.py` | `UpstreamPool` — role-based routing, health checks |
| `config.py` | `Config` — YAML + env var configuration |
| `state.py` | `State` — JSON persistence for phase state |
| `events.py` | `EventBus` — async event bus for SSE streaming |
| `gates.py` | `GateRegistry` — human approval gate management |
| `git.py` | `GitOps` — git operations (init, commit, tag, rollback) |
| `logger.py` | Structured JSONL logging per phase |
| `sprint_plan.py` | Sprint plan parsing and task slicing |
| `validators.py` | Phase output validators |

### `web/`

| Directory | Purpose |
|---|---|
| `backend/` | FastAPI application, routes, middleware |
| `frontend/` | Vanilla TypeScript PWA, hash routing, Service Worker |

### `orchestrator/cli/`

| Module | Purpose |
|---|---|
| `inspect.py` | CLI for project inspection, session dumps, token stats |

## Data flow

1. **Ingestion**: User provides project description → `qwendea.md`
2. **Architect**: Reads `qwendea.md` → produces `sprint-plan.md`
3. **Human gate**: User approves sprint plan
4. **Coder**: Reads `sprint-plan.md` → creates source files
5. **Tester**: Re-runs evidence commands → produces `TEST_REPORT.md`
6. **Reviewer**: Compares code to plan → produces `REVIEW.md`
7. **Human gate**: User approves review
8. **Deployer**: Produces `DEPLOY.md`

## Context budget

Qwen3.6 has a 131K token context window. Per-call soft caps:

| Component | Target | Hard cap |
|---|---|---|
| System prompt | ≤ 2K | 4K |
| Design docs | ≤ 8K | 12K |
| Task context | ≤ 30K | 60K |
| Reserved for generation | ≥ 16K | — |

**Total input budget: ~50K tokens per call.**

## Error handling

| Category | Strategy |
|---|---|
| Content failure | Retry with corrective feedback |
| Thinking truncation | Bump `max_tokens` or trim prompt |
| Malformed JSON | Re-prompt with JSON-only constraint |
| Server 503/504 | Exponential backoff 1→2→4→8s, max 4 retries |
| Connection refused | Pause run, surface to PWA |
| Unclean working tree | Hard fail, human investigation |

## Git discipline

- One commit per task (made by orchestrator after Tester verifies)
- Commit message format: `phase-<N>(task-<M>): <task name>`
- Phase boundary tags: `phase-<N>-done` (annotated)
- Rollback: `git reset --hard <sha>` or `git reset --hard phase-<N>-done`

## Dry-run mode

Set `fake_llm` on the Orchestrator to swap in `FakeLLMClient`. The fake
returns canned responses keyed by role, enabling full pipeline testing
without real LLM calls.

```python
fake = FakeLLMClient(responses={
    'user': LLMResponse(content='...', ...),
    'default': LLMResponse(content='...', ...),
})
orch = Orchestrator(config=config, fake_llm=fake)
orch.run()  # Zero real LLM calls
```
