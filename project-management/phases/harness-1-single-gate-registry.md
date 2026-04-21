# Harness 1 - Single Gate Registry

## Goal

Make "intervene" real. Today the engine and the PWA each own a separate
in-memory `GateRegistry`; a gate decision posted from the PWA lands in a
registry the running engine never reads. This phase collapses them into one
and makes `require_human_approval` a **per-run opt-in** — the PWA is an
idle-RPG touch surface, not a "human is watching so gate everything" trigger.

## Why this is second

Harness 0 ensures we can *see* what the engine did. This phase ensures we
can *stop and steer* it **when we choose to**. Without this, the PWA's
approve/reject/edit UI is cosmetic — the engine auto-approves every gate
because `web/backend/runner.py:160` hardcodes `require_human_approval=False`
with a literal "PWA gate flow not wired yet" comment. The fix is not to
coerce gates on for every PWA run, but to make the gate policy a real
user-controlled choice that the runner and engine both honor.

## Required Context

- `orchestrator/lib/gates.py:34` — the canonical `GateRegistry`
- `web/backend/routes/gates.py:60` — the duplicate `GateRegistry` to delete
- `web/backend/routes/gates.py:101` — module-level singleton (`_gate_registry`)
- `web/backend/runner.py:160` — the hardcoded auto-approval
- `web/backend/tests/test_gates.py` — current route tests (to extend, not replace)
- `orchestrator/engine.py:37-68` — engine accepts `gate_registry` parameter and
  lazily instantiates its own if none is passed

## Implementation Surface

- Delete: the duplicate `GateRegistry` class in `web/backend/routes/gates.py`.
- Wire: `web/backend/runner.py` constructs one `GateRegistry` and injects it
  into both `Orchestrator(gate_registry=...)` and FastAPI `app.state`.
- Expose: `require_human_approval` as a per-run parameter on the start-run
  API (defaults to **False** — idle-RPG mode). When a caller opts in, it
  flows all the way to the engine and the PWA shows the gate blockers live.
- Surface: `web/backend/routes/gates.py` becomes a thin HTTP facade over the
  canonical registry, not an owner.

## Task H1.1 - Consolidate GateRegistry

Status: Not started

Actions:

- Remove `class GateRegistry` and `_gate_registry = GateRegistry()` from
  `web/backend/routes/gates.py`.
- Replace `get_gate_registry()` with a FastAPI dependency that reads from
  `app.state.gate_registry` (populated at startup by the runner).
- Import the canonical type from `orchestrator.lib.gates`.
- Verify the canonical `GateRegistry` exposes every method the routes need:
  `open`, `decide`, `wait`, `get_rejection_reason`, plus any list/snapshot
  method the GET routes rely on. Extend the canonical class if a method
  is missing — do not reintroduce a shadow class.

Acceptance:

- `rg "class GateRegistry" web/ orchestrator/` returns exactly one match.
- All existing route tests in `web/backend/tests/test_gates.py` still pass
  against the consolidated registry.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_gates.py
```

## Task H1.2 - Inject Registry Into Engine From Runner

Status: Not started

Actions:

- In `web/backend/runner.py`, construct one `GateRegistry` per project run.
- Pass it to `Orchestrator(gate_registry=registry, ...)`.
- Publish the same instance on `app.state.gate_registry` so the HTTP routes
  operate on the engine's live registry.
- Remove the lazy fallback in `engine.py:64-68` — or keep it but emit a
  prominent warning log when it fires, so unit tests still work but any
  production path without a wired registry is visible.

Acceptance:

- An integration test starts the engine in-process, POSTs a gate decision
  via FastAPI `TestClient`, and asserts the engine unblocks and advances.
- The reverse: POSTing a `rejected` decision causes the engine to abort the
  phase with the rejection reason from the HTTP payload.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_gate_engine_integration.py
```

## Task H1.3 - Expose require_human_approval As A Per-Run Toggle

Status: Not started

Framing: the PWA is an idle-RPG touch surface. "Human opened the web app"
is not the same as "human wants to gate every step." Gate-on must be an
explicit, per-run opt-in — the human can kick off a run in idle mode and
later decide to *step in* by starting a new gated run (or, eventually,
flipping a live toggle that promotes the next gate into a real blocker).

Actions:

- Plumb `require_human_approval: bool` (default **False**) through
  `start_run` / `start_run_async` in `web/backend/runner.py` and into the
  `Config` passed to `Orchestrator`. Delete the `# H1.3 flips this` comment.
- Accept `require_human_approval` on the HTTP start-run route (body or
  query param), defaulting to False. Persist the chosen value alongside
  the run record so the PWA can reflect it.
- Surface a toggle on the PWA start panel ("Gate my approval at each
  phase"). Default off. When on, the PWA's gate view is the primary
  interaction surface for that run.
- Keep the CLI default `require_human_approval=False`. Add an explicit
  `--gate` (or `--require-approval`) flag for attended runs and document
  it in the CLI help. No `--auto-approve` flag — auto is already the
  default, so the flag is unnecessary noise.
- Out of scope for H1.3 (tracked separately): live mid-run promotion of
  an idle run into a gated run. That needs a different control plane
  (watchdog + next-gate-only opt-in) and should not block H2.

Acceptance:

- Starting a run with no approval flag (PWA default, CLI default) runs
  end-to-end without blocking — idle-RPG mode is preserved.
- Starting a run with the toggle on (PWA) or `--gate` (CLI) blocks at the
  first gate until a decision is POSTed, and the PWA reflects the pending
  state live.
- The runner no longer hardcodes the flag; both values flow from caller
  input through the `Config` into the engine.

Evidence:

```bash
uv run pytest -q web/backend/tests/test_runner.py web/backend/tests/test_gate_engine_integration.py
uv run pytest -q
grep -n "require_human_approval" web/backend/runner.py
```

## Phase Exit Criteria

- Exactly one `GateRegistry` class in the codebase.
- Gate-on is a real per-run user choice; idle-RPG default is preserved.
- Integration test proves round-trip for gated runs: POST decision →
  engine advances. A separate test proves idle runs never block.
- `runner.py` no longer contains the "not wired yet" TODO, and the
  `require_human_approval` value in `Config` is the caller's choice, not
  a literal.
