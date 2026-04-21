# Harness 6 — Opencode as Agent Runtime

**Status:** Draft (not yet approved). Pivots the hot path established
by H5 from direct `/v1/chat/completions` calls to driving
[`opencode`](https://opencode.ai) as the agent runtime for every role.

## Why this is its own phase

H0–H5 built an honest direct-LLM pipeline: `LLMClient` → OpenAI SDK →
configured endpoint, with our own raw-io / usage / pool observability.
That works, but it reimplements what `opencode` already gives for free:

- File ops (read / write / patch) inside a sandboxed agent loop.
- Tool invocation (shell, grep, edit, git) with structured results.
- Session recording — messages, tool calls, tokens, cost — on disk.
- Provider/model abstraction with streaming, caching, retry.

Hand-rolling all of that inside our role code means the coder role is a
"LLM returns a JSON blob of files" stub, the tester role shells out by
hand, and reviewer sees a frozen snapshot instead of a live edit
trace. Opencode as the runtime is a better primitive match.

Greenfield pivot, not a migration — there is nothing to preserve.
Direct-LLM infra (`LLMClient`, `SyncPoolClient`, `UpstreamPool`,
`pool.jsonl`, `raw-io.jsonl` as written by `log_llm_call`) all get
replaced or re-sourced from opencode sessions.

## End state

- Each role boots an opencode session with a role-specific prompt +
  role-appropriate tool allowlist + the configured provider/model.
- Role "execution" = `opencode run ...` (or equivalent non-interactive
  API) exits with the session on disk.
- Engine harvests the session (messages, tool calls, tokens, file
  edits, exit status) and advances state accordingly.
- Our audit trail (`raw-io.jsonl`, `usage.jsonl`, `pool.jsonl` or its
  replacement) is a view over opencode sessions, not a parallel log.
- Config still owns **what** (which provider, which model, which role
  uses which combination). Opencode's `opencode.json` owns **how**
  (SDK wiring). We generate opencode's config from ours so operators
  declare endpoints once.

## What stays, what goes

| Survives | Changes shape | Deletes |
| --- | --- | --- |
| `orchestrator/engine.py` state machine | Roles shell to opencode instead of calling `self.llm.chat` | `orchestrator/lib/llm.py` LLMClient (or becomes a thin fallback) |
| `orchestrator/lib/events.py` bus + gate registry | `log_llm_call` → `log_opencode_session` | `orchestrator/lib/sync_pool.py` |
| `orchestrator/lib/endpoints.py` config loader | Emits `opencode.json` fragments, not `UpstreamPool` | `orchestrator/lib/pool.py`, `pool_log.py` |
| `orchestrator/lib/raw_io.py`, `usage_writer.py`, `usage_summary.py` | Readers of opencode session data, not writers | — |
| Gate registry, SSE bridge, PWA | Unchanged | — |
| Role prompts (architect / coder / tester / reviewer / deployer) | Adapted for an agent-with-tools runtime, not a single-shot completion | — |

The H5 config contract (declarative `endpoints:` + `routing:` block,
per-role model override, env overrides) is the right operator-facing
shape and stays. Implementation underneath is what flips.

## Open questions (resolve before H6.1 starts)

1. **Non-interactive mode.** Does opencode expose `opencode run
   "<prompt>" --session <id> --json-output` or equivalent? If it only
   has a TUI, H6 is much harder. *Action: H6.0.*
2. **Session format on disk.** `~/.local/share/opencode/storage/`
   has `session_diff/ses_*.json` (file diffs only — not messages) plus
   `opencode.db` SQLite. Messages + tool calls likely live in the DB.
   *Action: H6.0 — confirm and document the schema we'll read.*
3. **Streaming.** Opencode's SDK uses `ai-sdk` which streams natively.
   Can we subscribe from Python, or do we poll the DB / tail a file?
   *Action: H6.0 — decide polling vs. subscription.*
4. **Provider config coupling.** Today's `endpoints:` YAML lets the
   operator put API keys behind env vars. Opencode's `opencode.json`
   takes inline keys. Can we templatize (opencode reads env too)?
   *Action: H6.2 when we generate the config.*
5. **Gate semantics.** A gate today is "engine pauses, PWA approves,
   engine continues." If opencode is mid-session, gating means
   either (a) interrupting opencode or (b) only gating between role
   sessions. *Action: H6.3 — spec this explicitly.*

## Task breakdown

### H6.0 — Spike: opencode as a callable runtime

Read-only research. Confirm the contract before writing any new code.

- Install opencode on this host (`npm i -g opencode` or platform
  package). Record exact version.
- Find the non-interactive invocation path. Read `opencode --help`
  end-to-end. Capture the smallest command that runs a prompt against
  a configured provider and exits with a session id.
- Reverse-engineer session storage. Query `opencode.db` schema;
  inventory `storage/session_diff/`. Document how to recover:
  *messages (user + assistant + tool), tool calls with args + results,
  token counts per message, model id, total cost, terminal exit code*.
- Decide streaming strategy: opencode SSE/WS endpoint vs. DB polling
  vs. tailing JSONL. Justify the choice in the phase evidence log.

**Evidence:** a working transcript in
`docs/research/opencode-runtime.md` with the exact command, the
exact session id returned, and parsed fields from the session.

### H6.1 — Generate `opencode.json` from `config.yaml`

- New `orchestrator/lib/opencode_config.py` that takes an
  `EndpointsConfig` and emits an `opencode.json` fragment (one provider
  per endpoint, one model entry per declared model).
- Write the generated config under `<project_dir>/.orchestrator/opencode/opencode.json`;
  never mutate the user's `~/.config/opencode/opencode.json`.
- Tests: given a two-endpoint config + two-model routing, assert the
  generated JSON validates against opencode's schema and covers every
  role's declared (endpoint, model) pair.

### H6.2 — `OpencodeSession` adapter

- New `orchestrator/lib/opencode.py`:
  - `OpencodeSession(config_path, provider, model, project_dir).run(prompt, *, tools=None, timeout=...)` →
    `OpencodeResult(session_id, messages, tool_calls, usage, exit_code)`.
  - Internally spawns `opencode run` (or library call if one exists),
    waits for exit, reads the session from disk, parses it.
  - No orchestrator imports — this is pure plumbing, unit-testable.
- Tests mock the opencode binary with a fixture that writes a fake
  session, then assert the adapter returns the right shape.

### H6.3 — Role rewrites

One role per sub-task, shipping incrementally. Order:

- H6.3a **Coder** first — biggest win, most natural fit for an agent
  loop. Role prompt becomes "do the work, write the files, report
  done." No more "return a JSON of files and let the engine write."
- H6.3b **Tester** — agent can run its own pytest, interpret failures,
  iterate (bounded by max attempts).
- H6.3c **Reviewer** — reads the diff the coder produced, comments.
- H6.3d **Deployer** — constrained tool allowlist (no network unless
  opted in).
- H6.3e **Architect + judge** — these are JSON-shaped single-shots.
  Keep them on a direct LLMClient (or a no-tools opencode invocation),
  decide in H6.0.

Each sub-task: rewrite the role, rewrite its tests, update its
integration test expectations, update the dry-run fixture.

### H6.4 — Audit trail replacement

- `raw_io.jsonl` readable via `orchestrator/lib/raw_io.py` becomes a
  view over opencode sessions — same on-disk path, same schema, but
  sourced from parsing the session, not from `log_llm_call`.
- `usage.jsonl` likewise — populated from opencode's token/cost output.
- Delete `pool.jsonl` + `pool_log.py` (opencode doesn't fail over
  between endpoints; if we need fallback later we add it back).
- Delete `SyncPoolClient`, `UpstreamPool`, `LLMClient` if H6.3e decides
  against retaining a direct path.
- `usage_summary.rollup()` still works — input format is unchanged.

### H6.5 — Gates interact with sessions correctly

- Decide and implement: does a gate pause between role sessions
  (simple) or mid-session (complex, requires interrupting opencode)?
- Propose "between-sessions only" for v1. Roles that today pause mid-
  execution get restructured into two role sessions with a gate in
  between.

### H6.6 — End-to-end guardrail

- `tests/test_integration_h6_opencode_pipeline.py`: spin up a fake
  opencode (a shell script in `tmp_path/bin/` on PATH) that consumes a
  prompt + writes a known-shape session + exits, then run the full
  engine and assert every role's session was harvested and the
  expected artifacts landed.

## Risks

- **Opencode is a moving target.** Pinning a version is mandatory;
  record it in `package.json` or a repo-level tool-versions file.
- **Streaming assumption could be wrong.** If opencode is poll-only,
  the PWA's live SSE view degrades to "heartbeat every N seconds."
  The tradeoff is probably worth it but must be explicit.
- **Binary not on this dev machine.** H6.0 must resolve this; without
  it nothing else can be written honestly.
- **Gate semantics regression.** If we can't interrupt a session, some
  today-possible gates become impossible. Note which.
- **Cost of agent loops vs. single-shot.** Coder-as-agent burns more
  tokens than coder-as-completion. Track in H6.3a evidence.

## Evidence log

Append here as tasks land.
