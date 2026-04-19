# Phase 1: Foundation

Core infrastructure every other phase builds on.

## Scope

- HTTP client for llama-server (OpenAI-compatible, with
  `reasoning_content` handling).
- Project state persistence.
- Config loading.
- Unit tests for all of the above.

## Dependencies

None. This is the first phase.

## Design

### `orchestrator/lib/llm.py` — LLM client

Wraps the `openai` SDK pointed at llama-server.

```python
from dataclasses import dataclass
from openai import OpenAI

@dataclass
class LLMResponse:
    content: str
    reasoning: str
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    finish_reason: str

class ThinkingTruncation(Exception):
    def __init__(self, reasoning_len: int):
        self.reasoning_len = reasoning_len

class LLMClient:
    def __init__(self, base_url: str, api_key: str = "placeholder"):
        self._client = OpenAI(
            base_url=f"{base_url}/v1",
            api_key=api_key,
            timeout=600,
        )

    def chat(
        self,
        messages: list[dict],
        *,
        max_tokens: int = 8192,
        temperature: float | None = None,
    ) -> LLMResponse:
        """Raises ThinkingTruncation on finish_reason=length with empty content."""
        ...

    def health(self) -> bool:
        """GET /health → True on {'status':'ok'}."""
        ...
```

Implementation notes:

- Parse `reasoning_content` via
  `getattr(msg, "reasoning_content", "") or ""`.
- If `finish_reason == "length"` and `content.strip() == ""` →
  raise `ThinkingTruncation`.
- Log `usage` for every call.
- HTTP 5xx: exponential backoff per `reference/error-handling.md`.
- Connection refused: raise immediately — don't mask server downtime.

### `orchestrator/lib/state.py` — State persistence

```python
class State:
    project_dir: Path
    state_file: Path  # project_dir / ".orchestrator/state.json"
    current_phase: str | None
    sessions: dict[str, str]       # phase -> session id
    retries: dict[str, int]
    gates_approved: dict[str, bool]

    def save(self) -> None: ...   # atomic: write .tmp, rename
    def load(self) -> None: ...   # tolerate missing file / missing keys
    def read_file(self, name: str) -> str: ...
    def write_file(self, name: str, content: str) -> None: ...
```

- JSON, atomic write (write to `.tmp`, rename).
- `.orchestrator/` directory auto-created on first save.
- Load is idempotent and tolerates partial / missing fields.

### `orchestrator/lib/config.py` — Config

```python
@dataclass
class Config:
    llama_server_url: str
    project_dir: Path
    max_retries: int = 3
    max_total_iterations: int = 20
    architect_max_passes: int = 3
    architect_pass_threshold: int = 4   # of 6
    quiz_min_turns: int = 3
    quiz_max_turns: int = 10
    require_human_approval: bool = True
    expose_public: bool = False          # LAN-only by default

    @classmethod
    def from_yaml(cls, path: Path) -> "Config": ...
    @classmethod
    def from_env(cls) -> "Config": ...   # env overrides yaml
```

## Tasks

### Task 1: Project skeleton
- **Priority**: P0
- **Files**: `orchestrator/__init__.py`, `orchestrator/lib/__init__.py`,
  `pyproject.toml`, `tests/__init__.py`

**Acceptance Criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `python -c "import orchestrator"` works

**Evidence Required:**
- Run `pip install -e .` and capture success output
- Run `python -c "import orchestrator; print(orchestrator.__file__)"`

### Task 2: LLM client
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/llm.py`, `tests/test_llm.py`

**Acceptance Criteria:**
- [ ] `LLMClient.chat()` parses both `content` and `reasoning_content`
- [ ] Mid-thinking truncation raises `ThinkingTruncation`
- [ ] `health()` hits `/health` endpoint
- [ ] HTTP 5xx triggers exponential backoff (1,2,4,8s; max 4 retries)
- [ ] Connection refused raises immediately without retry

**Evidence Required:**
- Run `pytest tests/test_llm.py -v` and observe all tests pass
- Mock llama-server with `respx` or `httpx_mock`; verify retry behavior
- Integration test (gated on `LLAMA_SERVER_URL` env var): call real
  server with "Write one sentence about the sea" and assert response
  has non-empty `content` OR `reasoning` fields

### Task 3: State persistence
- **Priority**: P0
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/state.py`, `tests/test_state.py`

**Acceptance Criteria:**
- [ ] `State.save()` writes atomically (tmp + rename)
- [ ] `State.load()` tolerates missing file (returns defaults)
- [ ] `State.load()` tolerates partial JSON (missing keys → defaults)
- [ ] `read_file` / `write_file` use `project_dir`-relative paths

**Evidence Required:**
- Run `pytest tests/test_state.py -v`
- Atomic-write test: mock `os.replace` to raise; verify no corrupted
  file remains

### Task 4: Config loading
- **Priority**: P1
- **Dependencies**: Task 1
- **Files**: `orchestrator/lib/config.py`, `tests/test_config.py`,
  `config.example.yaml`

**Acceptance Criteria:**
- [ ] Loads from YAML
- [ ] Environment variables override YAML values
- [ ] `expose_public` defaults to `False`
- [ ] Invalid YAML raises clear error (not a bare exception)

**Evidence Required:**
- Run `pytest tests/test_config.py -v`
- Round-trip: write YAML → load → compare struct

## Phase exit criteria

- All tasks above have filled Evidence Logs verified by Tester.
- `pytest orchestrator/tests/` passes with 0 failures.
- `LLMClient` successfully calls real llama-server and returns a parsed
  response (integration test).

## What's next

Phase 2 (`phase-2-ingestion.md`) uses `LLMClient` and `State` from this
phase.
