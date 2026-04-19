# Phase 1: Foundation — Handoff

## What this phase built

Three modules in `orchestrator/lib/`:

- **`orchestrator/lib/llm.py`** — `LLMClient` wraps the OpenAI SDK for
  llama-server communication. Handles `reasoning_content` extraction via
  `getattr(msg, "reasoning_content", "")`, `ThinkingTruncation` detection
  on mid-thinking truncation (`finish_reason=length` + empty content), and
  exponential backoff (1→2→4→8s, max 4 retries) for HTTP 5xx / rate
  limits. Connection refused raises immediately. `health()` checks
  `GET /health`.

- **`orchestrator/lib/state.py`** — `State` class persists project state
  to JSON at `.orchestrator/state.json`. Atomic writes via tmp+rename.
  `load()` tolerates missing files and partial JSON. `read_file`/`write_file`
  operate on `project_dir`-relative paths.

- **`orchestrator/lib/config.py`** — `Config` dataclass with YAML loading
  (`from_yaml`) and env-var overrides (`from_env`). Supports legacy
  `LLAMA_SERVER_URL` and new `LLAMA_PRIMARY_URL` vars. Validates
  required fields (`llama_server_url`, `project_dir`).

Entry points: `LLMClient(base_url, api_key)`, `State(project_dir)`,
`Config.from_yaml(path)`, `Config.from_env()`.

## Wired vs. stubbed

**Wired (tested, runnable):**
- `LLMClient.chat()` — fully mocked tests for parsing, truncation, retries.
  Integration test gated on `LLAMA_SERVER_URL` env var (skipped here).
- `LLMClient.health()` — mocked tests for ok/non-ok/error responses.
- `State.save()`/`load()` — atomic write, tolerance tests, round-trip.
- `State.read_file()`/`write_file()` — create, overwrite, subdirs, not-found.
- `Config.from_yaml()` — full/minimal config, defaults, missing fields,
  invalid YAML, hyphenated keys, round-trip.
- `Config.from_env()` — minimal env, legacy URL fallback, precedence.

**Stubbed / not built:**
- No llama-server is running; integration test for `LLMClient.chat()`
  against a real server is skipped.
- No PWA, no FastAPI, no phase engine, no role agents.
- No `sprint-plan.md` task slicer (`slice_task()`).
- No Evidence Log applier (patch JSON → markdown).
- No LAN-only middleware.

## Known gaps / deferred

Phase 2 (Ingestion) needs:
- `LLMClient` instantiated and working against a real llama-server.
  Start `llama-server` before running Phase 2.
- `State` for a concrete project directory (Phase 2 creates it).
- `Config` loaded from YAML + env vars (already available).

Phase 3 (Architect) needs:
- Context budget slicing (`slice_task(sprint_plan_md, task_id)`).
- Self-evaluation loop with adversarial judge prompt.
- Evidence Log patch JSON applier.

## Anything the next phase must know

- **`openai` SDK 2.x** is installed. The `reasoning_content` attribute
  lives on `choice.message`, accessed via `getattr(msg, "reasoning_content", "")`.
  This matches the upstream contract in `reference/upstream-contract.md`.
- **`respx`** is the mock library (not `httpx-mock`, which is listed in
  dev deps but not installed). Use `respx.mock` for HTTP mocking in tests.
- **`config.example.yaml`** is the reference config. Phase 2 should
  copy or reference it; do not modify it.
- The `orchestrator` package is installed editable (`pip install -e .`).
  Changes to source are reflected immediately — no reinstall needed.
- **No phase tag exists yet.** Phase 1 should be tagged `phase-1-done`
  after the handoff commit.
- **pytest is installed system-wide** at `/opt/homebrew/bin/pytest`.
  The bootstrap verifier runs `pytest` directly (not via venv), so it
  must be available in PATH.
