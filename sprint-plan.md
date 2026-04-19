# Sprint Plan

## Overview
Phase 1 establishes the core infrastructure: LLM client for llama-server communication, project state persistence, and config loading. These components form the foundation for all subsequent phases.

## Architecture Decisions
- Use the `openai` Python SDK (OpenAI-compatible protocol) for llama-server communication
- JSON-based state persistence with atomic writes (tmp + rename pattern)
- YAML config file with environment variable overrides
- All code in `orchestrator/lib/` package

## Tasks

### Task 1: Project skeleton
- **Priority**: P0
- **Dependencies**: none
- **Files**: `orchestrator/__init__.py`, `orchestrator/lib/__init__.py`,
  `pyproject.toml`, `tests/__init__.py`

**Acceptance Criteria:**
- [ ] `pip install -e .` succeeds
- [ ] `python -c "import orchestrator"` works

**Evidence Required:**
- Run `pip install -e .` and capture success output
- Run `python -c "import orchestrator; print(orchestrator.__file__)"`

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```Successfully built orchestrator / Successfully installed orchestrator-0.1.0```
- [ ] Import verified: `/Users/karol/dev/projects/llm-projects/build/workspace/orchestrator/__init__.py`
- [ ] Committed as f573d44


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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Mock tests verify retry behavior
- [ ] Integration test passes (if LLAMA_SERVER_URL set)
- [ ] Committed as <short-sha>


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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Atomic-write test passes
- [ ] Committed as <short-sha>


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

**Evidence Log:** (filled by Coder, verified by Tester, committed by orchestrator)
- [ ] Test command run, output recorded: ```<actual output>```
- [ ] Round-trip test passes
- [ ] Committed as <short-sha>


## Risks & Mitigations
1. llama-server unavailable → Integration tests gated on LLAMA_SERVER_URL env var
2. OpenAI SDK version changes → Pin minimum version in pyproject.toml
3. YAML parsing errors → Validate config schema on load
