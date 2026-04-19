# Phase 5: Orchestrator Engine

Wire the phases together. Phase state machine, retries, validators,
human gates, the upstream queue. This is the core runtime.

## Dependencies

- Phases 1-4 complete.

## Design

### `orchestrator/engine.py`

```python
class PhaseFailure(Exception): ...

class Orchestrator:
    def __init__(self, config: Config):
        self.config = config
        self.state = State(config.project_dir)
        self.llm = LLMClient(config.llama_server_url)
        self.queue = UpstreamQueue(self.llm)  # serializes around -np 1
        self.events = EventBus()              # for PWA SSE stream

    def run(self) -> None:
        """Execute the full SDLC pipeline. May pause at gates."""
        self._ensure_git_repo()   # git init if needed; seed .gitignore
        self._ensure_qwendea()
        self._run_phase("architect",     self._architect)
        self._gate("approve_sprint_plan")
        self._run_phase("implementation", self._coder)
        self._run_phase("testing",        self._tester)
        self._run_phase("review",         self._reviewer)
        self._gate("approve_review")
        self._run_phase("deployment",     self._deployer)

    def _run_phase(self, name: str, fn) -> None:
        for attempt in range(self.config.max_retries):
            self.state.current_phase = name
            self.events.emit("phase_start", name=name, attempt=attempt)
            try:
                fn()
            except Exception as e:
                self.events.emit("phase_error", name=name, error=str(e))
                if attempt == self.config.max_retries - 1:
                    raise PhaseFailure(name) from e
                continue

            if self._validate(name):
                self.events.emit("phase_done", name=name)
                return
            # Validator failed — retry with failure context
            self.events.emit("phase_retry", name=name, attempt=attempt+1)
        raise PhaseFailure(name)

    def _gate(self, name: str) -> None:
        """Block until PWA records an approval decision."""
        ...
```

### Upstream queue

Because llama-server is `-np 1`, any attempt to issue two concurrent
requests gets serialized at the socket layer — with worse latency than
a proper queue. Build an `asyncio.Queue`-backed serializer:

```python
class UpstreamQueue:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self._lock = asyncio.Lock()

    async def chat(self, messages, **kw) -> LLMResponse:
        async with self._lock:
            return await asyncio.to_thread(self.llm.chat, messages, **kw)
```

All role code goes through the queue, not the raw client. This lets
Phase 7 add parallelism by swapping the queue for a `-np > 1` pool
without touching role code.

### Validators

```python
# orchestrator/lib/validators.py

def validate_architect(state: State) -> tuple[bool, str]:
    """Returns (passed, failure_reason). Trusts Architect's internal
    self-eval — if sprint-plan.md is written, it already passed."""
    path = state.project_dir / "sprint-plan.md"
    if not path.exists():
        return False, "sprint-plan.md not written"
    content = path.read_text()
    if "Evidence Required:" not in content:
        return False, "no Evidence Required sections"
    return True, ""

def validate_implementation(state: State) -> tuple[bool, str]:
    """Every task has filled Evidence Log."""
    ...

def validate_testing(state: State) -> tuple[bool, str]:
    """TEST_REPORT.md has no MISMATCH or RERUN_FAILED."""
    report = (state.project_dir / "TEST_REPORT.md").read_text()
    for bad in ("MISMATCH", "RERUN_FAILED"):
        if bad in report:
            return False, f"TEST_REPORT contains {bad}"
    return True, ""

def validate_review(state: State) -> tuple[bool, str]:
    """REVIEW.md verdict is APPROVED or APPROVED WITH NOTES."""
    review = (state.project_dir / "REVIEW.md").read_text()
    if "CRITICAL" in review:
        return False, "REVIEW marked CRITICAL"
    if "CHANGES REQUESTED" in review:
        return False, "REVIEW requested changes"
    return True, ""
```

**Note on validator strength**: these are structural checks. The
*semantic* validation happened upstream:
- Architect self-eval is the semantic gate for sprint-plan quality.
- Tester's re-run is the semantic gate for implementation.
- Reviewer's verdict is the semantic gate for code quality.

These Python validators only confirm the gates fired and the outputs
are structurally sound.

### Human gates

```python
class Gate:
    name: str
    artifact_path: str  # file the user should review
    decision: Literal["pending", "approved", "rejected"] = "pending"
    timeout_sec: int = 0  # 0 = wait forever
    decided_at: datetime | None = None

class GateRegistry:
    def open(self, gate: Gate) -> None: ...
    def decide(self, name: str, decision: str) -> None: ...
    def wait(self, name: str) -> str: ...  # blocks / polls
```

PWA endpoints (Phase 6) call `decide()`. Orchestrator calls `wait()`
and proceeds or raises based on decision.

**Defaults**:
- `require_human_approval=True` in config
- `timeout_sec=0` (wait forever)
- Rejection stores the user's reason (optional text) and fails the
  phase with that as failure context

### Event bus (for PWA progress stream)

```python
class EventBus:
    def emit(self, type: str, **fields) -> None: ...
    async def subscribe(self) -> AsyncIterator[dict]: ...
```

Events: `phase_start`, `phase_retry`, `phase_done`, `phase_error`,
`llm_call` (with usage stats), `gate_opened`, `gate_decided`,
`evidence_written`, `escalation`.

PWA's SSE endpoint (Phase 6) tails this bus.

### Git operations

Per `reference/git-policy.md`, the orchestrator owns all git writes —
roles never commit directly. Minimal API in `orchestrator/lib/git.py`:

```python
class GitOps:
    def ensure_repo(self, project_dir: Path) -> None:
        """git init if not a repo; write .gitignore with .orchestrator/
        and language defaults; make initial commit of qwendea.md +
        sprint-plan.md after Architect gate."""

    def assert_clean(self) -> None:
        """Raise UncleanWorkingTree if `git diff-index --quiet HEAD --`
        is non-zero. Called before each task."""

    def commit_task(self, phase: str, task_id: int, name: str,
                    prior_head: str) -> str:
        """Stage all, commit with the mandatory message template,
        return the new short SHA."""

    def tag_phase(self, phase_num: int) -> None:
        """Annotated tag `phase-<N>-done` at HEAD."""

    def rollback_to(self, ref: str) -> None:
        """git reset --hard <ref>. Only called via explicit CLI;
        never automatic."""
```

Wire-up:
- `_run_phase` calls `assert_clean()` before handing to role.
- After Tester returns VERIFIED for task M, orchestrator calls
  `commit_task(...)`, then patches the Evidence Log with the SHA.
- On phase exit-criteria pass, orchestrator calls `tag_phase(N)`.

## Tasks

### Task 1: Engine skeleton
- **Priority**: P0
- **Files**: `orchestrator/engine.py`, `tests/test_engine.py`

**Acceptance Criteria:**
- [ ] `Orchestrator.run()` calls phases in the correct order
- [ ] `_run_phase` retries on validator failure up to `max_retries`
- [ ] Exception in role propagates (wrapped as `PhaseFailure`) after
      exhausting retries
- [ ] State persisted after every phase transition

**Evidence Required:**
- `pytest tests/test_engine.py -v`
- Mock roles; assert call order

### Task 2: Upstream queue
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/queue.py`, `tests/test_queue.py`

**Acceptance Criteria:**
- [ ] Concurrent calls serialize (no interleaving)
- [ ] Exception in one call doesn't deadlock queue
- [ ] Async-safe (multiple coroutines can `await` without issue)

**Evidence Required:**
- `pytest tests/test_queue.py -v`
- Concurrency test: 5 parallel `await queue.chat()` calls; assert
  observed serial execution

### Task 3: Validators
- **Priority**: P0
- **Dependencies**: Phase 4 complete
- **Files**: `orchestrator/lib/validators.py`,
  `tests/test_validators.py`

**Acceptance Criteria:**
- [ ] Each validator returns `(bool, str)`
- [ ] `validate_testing` catches MISMATCH and RERUN_FAILED
- [ ] `validate_review` catches CRITICAL and CHANGES REQUESTED
- [ ] Missing-file cases handled cleanly

**Evidence Required:**
- `pytest tests/test_validators.py -v`
- Fixture coverage for pass, structural fail, and semantic fail cases

### Task 4: Gates
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/gates.py`, `tests/test_gates.py`

**Acceptance Criteria:**
- [ ] `Gate.wait()` blocks until `decide()` is called
- [ ] Rejection propagates a failure reason into phase retry context
- [ ] Timeout=0 waits indefinitely; timeout>0 raises `GateTimeout`
- [ ] Multiple gates can be open concurrently (tracked by name)

**Evidence Required:**
- `pytest tests/test_gates.py -v`
- Async test: spawn `wait()` in one task, call `decide()` from another,
  assert unblocked

### Task 5: Git operations
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/git.py`, `tests/test_git.py`

**Acceptance Criteria:**
- [ ] `ensure_repo` creates repo + `.gitignore` idempotently
- [ ] `assert_clean` raises `UncleanWorkingTree` on dirty tree
- [ ] `commit_task` produces a commit whose message matches
      `^phase-\w+\(task-\d+\): ` and returns the short SHA
- [ ] `tag_phase` creates annotated `phase-<N>-done` tag
- [ ] `rollback_to` is NOT invoked automatically anywhere in engine

**Evidence Required:**
- `pytest tests/test_git.py -v` (uses tmp repo fixtures)
- Grep: `rg "rollback_to" orchestrator/` shows only CLI callers

### Task 6: Event bus
- **Priority**: P1
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/events.py`, `tests/test_events.py`

**Acceptance Criteria:**
- [ ] `emit()` reaches all subscribers
- [ ] Subscriber added after emit() does NOT see past events (live
      stream, not replay)
- [ ] Back-pressure on slow subscriber doesn't block emitter

**Evidence Required:**
- `pytest tests/test_events.py -v`

## Phase exit criteria

- All 6 tasks' Evidence Logs verified.
- **End-to-end test**: given a canned `qwendea.md` for a trivial project
  (e.g., "FizzBuzz as a CLI tool"), the orchestrator runs through all
  phases, emits expected events, opens expected gates, and produces
  working code with a non-CRITICAL REVIEW.md.

## What's next

Phase 6 (`phase-6-web-pwa.md`) — put a PWA in front of this engine.
