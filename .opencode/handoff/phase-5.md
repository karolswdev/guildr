# Phase 5 Handoff — Orchestrator Engine

## What this phase builds

The orchestrator engine — the "conductor" that wires together all six phases (Architect → Coder → Tester → Reviewer → Deployer) into a single pipeline with:
- Phase state machine with retry logic
- Per-phase validators (structural checks on artifacts)
- Human gate integration (approve_sprint_plan, approve_review)
- Upstream pool (PRIMARY/ALIEN endpoint routing)
- Git operations (commit, tag, rollback)
- Event bus (SSE streaming to PWA)

## Phase 5 tasks (parallel: T2-T6 depend only on T1)

| Task | File | Commit |
|------|------|--------|
| T1 | `orchestrator/engine.py` + `tests/test_engine.py` | `3464c09` |
| T2 | `orchestrator/lib/pool.py` + `tests/test_pool.py` | `9c7d0e3` |
| T3 | `orchestrator/lib/validators.py` + `tests/test_validators.py` | `203a5e5` |
| T4 | `orchestrator/lib/gates.py` + `tests/test_gates.py` | `4a6fac7` |
| T5 | `orchestrator/lib/git.py` + `tests/test_git.py` | `3b8fb36` |
| T6 | `orchestrator/lib/events.py` + `tests/test_events.py` | `8c1bd96` |

## Architecture decisions

- **Lazy imports**: Engine skeleton uses lazy property getters (`_events_obj`, `_gate_registry_obj`, `_git_ops_obj`) so it can be tested independently before Tasks 2-6 modules exist.
- **Validators return `(bool, str)`**: Each validator returns (passed, reason) tuple for debugging.
- **PhaseFailure exception**: Wraps all phase failures with `phase_name` attribute and preserves original exception as `__cause__`.
- **State persistence**: `State.save()` called after every phase transition (start, done, gate decision).

## Key files and modules

| File | Purpose |
|------|---------|
| `orchestrator/engine.py` | `Orchestrator` class — phase state machine, retries, validators, gates |
| `orchestrator/lib/pool.py` | `UpstreamPool` — async endpoint routing with PRIMARY/ALIEN |
| `orchestrator/lib/validators.py` | Per-phase structural validators (sprint-plan, TEST_REPORT, REVIEW) |
| `orchestrator/lib/gates.py` | `GateRegistry` — thread-safe gate with `threading.Condition` |
| `orchestrator/lib/git.py` | `GitOps` — real git operations via subprocess |
| `orchestrator/lib/events.py` | `EventBus` — async event bus with subscriber queues |

## Entry points

- `Orchestrator.run()` — executes full SDLC pipeline
- `Orchestrator._run_phase(name, fn)` — runs a single phase with retry logic
- `Orchestrator._validate(name)` — runs per-phase structural validator
- `Orchestrator._gate(name)` — blocks until human gate approval

## Wired vs. stubbed

**Wired (25 tests pass):**
- Phase order: architect → implementation → testing → review → deployment
- Retry logic: retries on validator failure up to max_retries
- Exception wrapping: role exceptions → PhaseFailure with preserved `__cause__`
- State persistence: `current_phase`, `retries`, `gates_approved` saved to JSON
- `_ensure_git_repo`: calls `git_ops.ensure_repo()`
- `_ensure_qwendea`: checks qwendea.md exists
- Validators: architect (sprint-plan exists + Evidence Required), implementation (evidence filled), testing (no MISMATCH/RERUN_FAILED), review (APPROVED verdict)

## Known gaps / deferred

- Context budget enforcement (token counting, reasoning strip)
- Queue design for single `-np 1` server slot
- Real llama-server integration (all tests mock `LLMClient`)

## Anything the next phase must know

- **`Orchestrator._gate`**: When `config.require_human_approval=False`, gate auto-approves. When `True`, calls `gate_registry.wait(name, timeout_sec=0)` which returns immediately (tests use `timeout_sec=0`).
- **`Orchestrator._validate`**: Unknown phase names return `True` (no validator defined). Only architect, implementation, testing, and review have validators.
- **`State.retries`**: Dict mapping phase name to number of attempts used (1-indexed, so first success = 1).
- **`State.gates_approved`**: Dict mapping gate name to bool.
- **Lazy modules**: When `pool`, `gate_registry`, `events`, or `git_ops` are `None` in `__init__`, the engine lazily imports from the respective modules on first access.
