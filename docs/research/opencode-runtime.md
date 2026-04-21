# Opencode as agent runtime — H6.0 spike findings

**Date:** 2026-04-21
**Opencode version:** `1.14.20` (`npm i -g opencode-ai`)
**Node:** `v22.21.0` (nvm)
**Host:** this Mac; LAN reachable via PRIMARY (`192.168.1.13:8080`)

Purpose: answer the open questions in
`project-management/phases/harness-6-opencode-agent-runtime.md`
**before** writing any H6 code.

## TL;DR

All four H6 open questions resolve favourably:

1. **Non-interactive mode.** `opencode run --format json` exits on
   completion and streams newline-delimited JSON events to stdout. No
   TUI coupling.
2. **Session format.** `opencode export <sessionID>` dumps a
   fully-formed JSON object (info + messages + parts) — canonical end-
   of-session record. Live events are on stdout during `run`.
3. **Streaming.** NDJSON on stdout. No need to poll the DB or subscribe
   over HTTP; just consume stdout line-by-line.
4. **Provider config.** `~/.config/opencode/opencode.json` already
   declares our PRIMARY/ALIEN endpoints via `@ai-sdk/openai-compatible`;
   we can generate a per-project overlay without touching the global
   config.

Greenfield path is clear. H6.1 can start.

## The core primitives

```bash
# Non-interactive run — prompt in, NDJSON events on stdout, exits on done.
opencode run \
  --model <provider>/<modelID> \
  --agent <agent_name> \
  --dir <project_dir> \
  --format json \
  --dangerously-skip-permissions \
  "<prompt>"

# Canonical session dump (after the run exits).
opencode export <sessionID>

# Headless HTTP+WS server (alternative — not needed for v1).
opencode serve --port <n>
```

`--format json` is the hinge: without it, `run` emits human-formatted
text to stdout; with it, every event the TUI would render becomes one
JSON object on one line, ending when the session terminates. This is
the streaming primitive H6 spins on.

`--dangerously-skip-permissions` auto-allows tool calls (the TUI would
otherwise prompt). Acceptable for agent-runtime use because our
permissions live in the per-role agent definition, not in interactive
prompts.

## Smoke transcript

### A: zero-tool, single text output

Command:
```bash
opencode run \
  --model primary/Qwen3.6-35B-A3B-UD-Q5_K_XL.gguf \
  --format json \
  --dangerously-skip-permissions \
  "Reply with the single word READY and nothing else."
```

Stdout (3 events, whitespace added):
```json
{"type":"step_start","timestamp":1776803998062,
 "sessionID":"ses_24e3af6dbffe8vYyoLlpPpAeFd",
 "part":{"id":"prt_…","messageID":"msg_…","type":"step-start"}}

{"type":"text","timestamp":1776803998272,
 "sessionID":"ses_24e3af6dbffe8vYyoLlpPpAeFd",
 "part":{"id":"prt_…","messageID":"msg_…","type":"text",
         "text":"READY",
         "time":{"start":1776803998260,"end":1776803998270}}}

{"type":"step_finish","timestamp":1776803998276,
 "sessionID":"ses_24e3af6dbffe8vYyoLlpPpAeFd",
 "part":{"id":"prt_…","reason":"stop",
         "messageID":"msg_…","type":"step-finish",
         "tokens":{"total":10380,"input":10358,"output":22,
                   "reasoning":0,"cache":{"write":0,"read":0}},
         "cost":0}}
```

Exit code: 0. Wall time: ~6s.

### B: tool-using session

Command:
```bash
opencode run \
  --model primary/Qwen3.6-35B-A3B-UD-Q5_K_XL.gguf \
  --format json \
  --dangerously-skip-permissions \
  --dir /tmp \
  "Create a file called /tmp/opencode-smoke.txt with the word HELLO,
   then list /tmp files starting with opencode-."
```

Event timeline (compacted):

| # | type | key fields |
| - | ---- | ---------- |
| 1 | `step_start` | — |
| 2 | `tool_use` | `tool:"write"`, `input:{content:"HELLO",filePath:"/tmp/opencode-smoke.txt"}`, `state.status:"completed"`, `output:"Wrote file successfully."` |
| 3 | `step_finish` | `reason:"tool-calls"`, `tokens.total:10465` |
| 4 | `step_start` | — |
| 5 | `tool_use` | `tool:"glob"`, `input:{pattern:"opencode-*",path:"/tmp"}`, `output:"/tmp/opencode-smoke.txt"` |
| 6 | `step_finish` | `reason:"tool-calls"`, `tokens.total:10539` |
| 7 | `step_start` | — |
| 8 | `text` | `text:"Done. Created …"` |
| 9 | `step_finish` | `reason:"stop"`, `tokens.total:10615` |

File was actually written on disk (verified `cat /tmp/opencode-smoke.txt`
→ `HELLO`). Each tool call carries `input`, `output`, `state.status`
(`completed` / `error`), and a `time.start/end` we can use for
latencies. Exit code 0.

### C: session export after the fact

`opencode export ses_24e3af6dbffe8vYyoLlpPpAeFd` dumps 146 lines of
JSON:

```json
{
  "info": {
    "id": "ses_24e3af6dbffe8vYyoLlpPpAeFd",
    "slug": "kind-pixel",
    "projectID": "global",
    "directory": "/Users/karol/dev/projects/llm-projects",
    "title": "Readiness check",
    "version": "1.14.20",
    "summary": {"additions": 0, "deletions": 0, "files": 0},
    "permission": [ … ],
    "time": {"created": 1776803973412, "updated": 1776803979547}
  },
  "messages": [
    {
      "info": {
        "role": "user",
        "agent": "build",
        "model": {"providerID": "primary",
                  "modelID": "Qwen3.6-35B-A3B-UD-Q5_K_XL.gguf"},
        "id": "msg_…",
        "sessionID": "ses_…"
      },
      "parts": [
        {"type": "text", "text": "\"Reply with READY…\"", …}
      ]
    },
    {
      "info": {
        "role": "assistant",
        "mode": "build",
        "tokens": {"total": 10380, "input": 10358, "output": 22, …},
        "cost": 0,
        …
      },
      …
    }
  ]
}
```

Every field we need for audit:

- `info.id` / `info.sessionID` — join key.
- `info.time.created/updated` — session bracket.
- `info.summary.{additions,deletions,files}` — quick health signal.
- `messages[].info.role` (`user` / `assistant`) — actor.
- `messages[].info.model.{providerID,modelID}` — which endpoint+model
  actually served the call. Replaces `pool.jsonl`'s `chosen_endpoint`
  + `chosen_model`.
- `messages[].info.tokens` + `messages[].info.cost` — replaces
  `usage.jsonl`.
- `messages[].parts[]` — the full transcript (text / tool / step events)
  replacing `raw-io.jsonl`'s round-trip record.

## Agents are first-class

`opencode agent list` returns named agents with their permission table:

```
build (primary)
  [
    {"permission":"*","action":"allow","pattern":"*"},
    {"permission":"doom_loop","action":"ask","pattern":"*"},
    {"permission":"external_directory","pattern":"*","action":"ask"},
    {"permission":"question","action":"deny","pattern":"*"},
    {"permission":"plan_enter","action":"deny","pattern":"*"},
    …
  ]
```

For H6.1 / H6.3 each role becomes its own agent:

- `architect` — no file writes, no shell; just text output.
- `coder` — `write` / `edit` allowed on project dir; shell restricted.
- `tester` — shell allowed for pytest / npm test; `write` denied
  outside of test artifacts directory.
- `reviewer` — read-only; `edit`/`write`/shell denied.
- `deployer` — explicit opt-in per-command allowlist.

Agent config format: JSON, same shape as `opencode debug agent build`
output. Likely lives under
`<project_dir>/.opencode/agents/<name>.json` (to confirm when we
generate one). This is where per-role tool allowlists land.

## Provider config

`opencode.json` uses `@ai-sdk/openai-compatible` for each provider —
identical shape to what our `orchestrator/lib/endpoints.py` already
parses. Mapping:

| `endpoints.py` field | `opencode.json` field |
| --- | --- |
| `EndpointSpec.name` | `provider.<name>` key |
| `EndpointSpec.base_url` | `provider.<name>.options.baseURL` (+ `/v1`) |
| `EndpointSpec.model` | `provider.<name>.models.<modelID>` key |
| `EndpointSpec.api_key` | `provider.<name>.options.apiKey` |
| `EndpointSpec.headers` | `provider.<name>.options.headers` (TBC) |

H6.1 generates a per-project
`<project_dir>/.orchestrator/opencode/opencode.json` from the same
`config.yaml` block we already parse. We don't touch
`~/.config/opencode/opencode.json` — too invasive, and it's the user's
personal session tool.

Per-project config location: opencode walks up from `--dir` looking
for `opencode.json`. Confirmed path is
`$OPENCODE_CONFIG` env override, else `<dir>/opencode.json`, else
`~/.config/opencode/opencode.json` — needs one more verification when
we actually generate the file.

## Global paths worth remembering

From `opencode debug paths`:

```
home    /Users/karol
data    /Users/karol/.local/share/opencode
bin     /Users/karol/.cache/opencode/bin
log     /Users/karol/.local/share/opencode/log
cache   /Users/karol/.cache/opencode
config  /Users/karol/.config/opencode
state   /Users/karol/.local/state/opencode
```

Under `data/storage/`: `session_diff/ses_*.json` (file-change diffs
per session — what we see in `info.summary`), plus `opencode.db`
SQLite and `opencode.db-{shm,wal}`. We read sessions via `opencode
export`, not SQLite — avoids coupling to private schema.

## Decisions locked for H6

1. **Invocation:** `opencode run --format json --dir <project_dir>
   --agent <role> --model <provider/model>
   --dangerously-skip-permissions "<prompt>"`. One role = one session
   = one process. Exit code surfaces success/failure.
2. **Live events → PWA:** subprocess stdout, line-by-line `json.loads`,
   re-emit onto the existing `SimpleEventBus`. Drop-in replacement for
   the engine's current `emit("phase_event", …)` calls inside a role.
3. **Audit record:** on session exit, run `opencode export
   <sessionID>` and persist the output. This replaces
   `raw-io.jsonl`, `usage.jsonl`, and `pool.jsonl`'s
   `chosen_endpoint`/`chosen_model`.
4. **Config generation:** per-project `.orchestrator/opencode/opencode.json`
   authored by `orchestrator.lib.opencode_config` (new in H6.1) from
   the same `endpoints:` block we already own.
5. **Agents:** one opencode agent per SDLC role, generated into
   `.orchestrator/opencode/agents/<role>.json`. Tool allowlists are
   declarative, version-controlled, code-reviewable.
6. **Gates:** between-sessions only for v1 (so session = atomic role
   execution). Revisit if we decide mid-session interruption is
   table-stakes.
7. **Streaming strategy:** **stdout NDJSON**, not HTTP `serve`. Fewer
   moving parts; the serve path stays available if we ever need
   multiple concurrent watchers on one session.

## Remaining unknowns (OK to discover during H6.1/H6.3)

- Exact agent-definition file format (have the shape, need the
  schema). Resolve by running `opencode debug skill` and generating
  one agent, then diffing against `opencode debug agent <name>`.
- Whether `--headers` on the CLI / headers in `opencode.json` options
  let us pass OpenRouter `HTTP-Referer` / `X-Title`. Fallback: set via
  env or omit OpenRouter until the SDK exposes it.
- Cost fields when the model is local — `cost:0` in this transcript
  because the SDK has no price sheet for local Qwen. Fine for local,
  but we need to confirm it populates correctly on OpenRouter /
  OpenAI so `usage_summary.rollup()` stays honest.
- Interrupt semantics if we later need mid-session gates: does
  sending SIGTERM leave a recoverable session? Not needed for v1.
