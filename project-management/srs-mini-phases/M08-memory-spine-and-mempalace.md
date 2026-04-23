# M08 — Memory Spine And MemPalace Integration

## Purpose

Make MemPalace the mandatory memory spine: every serious run refreshes memory, emits a wake-up packet, and carries that packet into compact context and operator prompt augmentation. Memory state, sync, search, and errors are first-class events and PWA surfaces.

## Why this phase exists

SRS §4.1 and §6.1 make memory non-optional. Current status already reports memory_refresh is implemented, but the PWA lens, error surfacing, and agent-wing coverage need hardening. Without durable memory+diffs, small-context models cannot succeed (SRS principle §4.2).

## Required context files

- `docs/srs-council-engine.md` §4.1, §4.2, §6.1
- `docs/research/opencode-runtime.md`
- `mempalace.yaml` (project-local config contract)
- `orchestrator/lib/memory_palace.py`
- `orchestrator/lib/control.py`
- `orchestrator/lib/opencode.py`
- `orchestrator/lib/opencode_config.py`
- `orchestrator/roles/memory_refresh.py` (or equivalent phase)
- `.orchestrator/memory/{wake-up.md,status.txt,last-search.txt}`
- `QUALITY_GATES.md` G1, G8

## Implementation surface

- `orchestrator/lib/memory_palace.py` (init, mine, wake-up, search, status)
- `orchestrator/lib/control.py` (compact context + operator prompt memory injection)
- `orchestrator/lib/opencode_config.py` (optional MemPalace MCP/tool exposure for selected agents)
- Memory events: `memory_refreshed`, `memory_status`, `memory_search_completed`, `memory_error`
- Backend routes under `/api/projects/{id}/memory/*`
- Frontend Mythos/Memory panel + memory body in scene
- Compact context composer (threads wake-up packet in)

## Current-state baseline

- MemPalace is already present as a project dependency and the local CLI reports `MemPalace 3.3.2`.
- `orchestrator/lib/memory_palace.py` already resolves `mempalace`, runs `init`, `mine`, `status`, `wake-up`, and `search`, and caches output under `.orchestrator/memory/`.
- `orchestrator/roles/memory_refresh.py` already calls `sync_project_memory()` and writes compact context.
- `orchestrator/lib/control.py` already appends the cached wake-up packet to operator context via `append_operator_context()`.
- Most opencode-backed roles already call `append_operator_context()`. Architect/judge have no tools, so prompt injection is mandatory for them. Coder/tester/reviewer/deployer can additionally inspect `.orchestrator/memory/*` through read/grep tools.
- OpenCode supports MCP servers through `opencode.json` under `mcp`, and per-agent tool enablement. MemPalace exposes an MCP server with `python -m mempalace.mcp_server`; use this only as an augmentation to deterministic wake-up packets.

## Integration architecture

Memory reaches opencode through two channels:

1. **Prompt channel, mandatory.** Every role prompt carries a bounded `Palace Wake-Up` section produced by MemPalace. This keeps zero-tool roles memory-aware and makes replay/provenance deterministic.
2. **Tool/MCP channel, optional.** Selected tool-enabled agents may query MemPalace through MCP or read `.orchestrator/memory/*`. This is for live lookup and exploration, not for replacing the wake-up packet.

The first shippable slice is **M08a — Memory Provenance Packet**:

- compute a stable hash for `.orchestrator/memory/wake-up.md`;
- emit `memory_refreshed` / `memory_status` payloads with `wake_up_hash`, `wing`, command availability, initialized state, and artifact refs;
- attach memory refs to loop events and next-step / DWA packets;
- fold memory events in the PWA so the operator can answer: "which memory packet influenced this step?"

Only after M08a is green should **M08b — MemPalace MCP For Opencode** add generated opencode MCP config for selected agents.

## Tasks

- [x] Ensure `memory_refresh` runs before planning phases as a workflow default.
- [x] Init MemPalace for a project if absent; mine project files into the project wing.
- [x] Write `.orchestrator/memory/wake-up.md` deterministically after mining.
- [x] Compute a stable wake-up packet hash and include it in memory status/sync responses.
- [x] Emit `memory_refreshed` with `wake_up_hash`, `wing`, command availability, initialized state, and memory artifact refs.
- [x] Surface memory errors as `memory_error` events (never swallow).
- [x] Backend routes: status / sync / wake-up / search. Scrub query inputs.
- [x] Include wake-up packet in compact context composer + operator prompt augmentation.
- [x] Verify every opencode-backed role either calls `append_operator_context()` directly or inherits it through `BaseRole._augment_prompt()`.
- [x] Add prompt-level provenance: opencode session audit or adjacent event records which wake-up hash was injected.
- [x] Add next-step / DWA memory refs so the narrative surface can cite the wake-up packet and relevant searches. Landed 2026-04-22: next-step packets, narrative digests, discussion entries, and discussion highlights carry `wake_up_hash` + `memory_refs`; Story Lens digest/discussion/highlight cards render those refs beside source/artifact refs.
- [x] PWA: memory body (radar/antenna prop) orbits the goal core; tap opens memory panel (status, last search, sync control, wake-up preview). Landed 2026-04-22: `memory-core:body`, `memory-core-control`, `memory-core-sheet`, replay-folded `memoryEvents`, and `/memory/sync` control.
- [x] Memory diffing hook: after each successful phase emits `memory_diff` with
  `previous_wake_up_hash`, `wake_up_hash`, and `hash_changed`.
- [x] Agent-specific wings: each SDLC role gets a wing scoped to its concerns (can be stubbed with empty wings v1). Landed 2026-04-22: `role_wings` reserves deterministic architect/coder/tester/reviewer/narrator/deployer/judge wings; role prompts inject the current phase wing; PWA memory card displays the wing contract.
- [x] OpenCode `mcp.mempalace` config using `python -m mempalace.mcp_server`, disabled globally and enabled only for selected tool-using agents. Landed 2026-04-22: MemPalace MCP is on by default for coder/tester/reviewer/narrator through `memory_mcp`; architect/judge are rejected; operators can set `memory_mcp.enabled: false` to remove it.

## Quality gates

- [x] G1 Event integrity on memory events.
- [x] G8 Security — search queries scrubbed; no secrets in `last-search.txt`.
- [x] G7 Cost — current memory operations are audited as external MemPalace CLI calls with no exposed token/cost payload. `memory_status` / memory events carry `cost_accounting.usage_recorded=false` with the reason; future orchestrator-owned embedding/provider calls must emit `usage_recorded`.
- [x] G4 No-dashboard — memory surface is a body + panel, not a tab grid.
- [x] G5 Source-ref credibility — every memory-backed narrative/DWA claim carries a memory/artifact/event ref.
- [x] G2 Replay determinism — replay uses the wake-up hash/refs known at that event index, not current memory state.

## Evidence commands / checks

```bash
uv run pytest -q orchestrator/tests/test_workflow.py web/backend/tests/test_memory.py web/backend/tests/test_control.py
# confirm wake-up.md appears in compact context
rg -n "wake-up.md|Palace Wake-Up|append_operator_context" orchestrator/lib orchestrator/roles tests
# confirm OpenCode config includes any intentionally enabled MCP only after M08b
rg -n "\"mcp\"|mempalace|mcp_server" orchestrator/lib/opencode_config.py tests docs
```

## Done means

- [x] A fresh project run initializes MemPalace, emits `memory_refreshed`, and writes wake-up.md.
- [x] Compact context and operator prompt include wake-up packet content.
- [x] Every opencode-backed role records or references the wake-up hash it received.
- [x] Next-step / DWA packets carry memory refs so the PWA can display memory provenance.
- [x] PWA shows memory status, last search, sync button, wake-up preview.
- [x] PWA shows role wings and current memory cost-accounting status.
- [x] Memory errors appear as events (not as silent warnings).
- [x] Hash changes across phases produce `memory_diff` with `hash_changed`.
- [x] Optional M08b only: generated opencode config can expose MemPalace MCP to selected tool-enabled agents without enabling it for zero-tool roles by accident.

## Known traps

- Making memory "best effort" silently hides broken wings. Promote failures to events.
- Blocking the main pipeline on slow mining: mining runs in its own phase with progress status; the agent thread should not wait inline beyond a cap.
- Search inputs can leak secrets into `last-search.txt` — scrub on write.
- Per-project vs global palace is an open question (SRS §16); pick per-project default, document the override.
- Relying on opencode session continuity for memory is wrong; each role invocation must receive the relevant wake-up packet or refs explicitly.
- Enabling MemPalace MCP globally can bloat tool context and make memory use nondeterministic. Keep deterministic wake-up injection as the primary channel.
- Zero-tool agents cannot fetch memory files or MCP results. If architect/judge need it, inject it.

## Handoff notes

- M05 Narrator may read memory diffs for richer digests.
- M09 tracks embedding model spend as `usage_recorded`.
- M02 next-step packets and M04/M05 DWA/narrative digests should call `memory_provenance()` and treat `wake_up_hash` + memory refs as first-class provenance.
- Proposed first delivery: M08a Memory Provenance Packet. Proposed second delivery: M08b MemPalace MCP for selected opencode agents.

## Evidence log

- 2026-04-22 M08a partial: `orchestrator/lib/memory_palace.py` computes stable `wake_up_hash`; `memory_refresh` emits `memory_refreshed` / `memory_error`; memory routes emit status/refresh/search/error events; opencode audit rows include `runtime.memory.wake_up_hash`; EventEngine folds memory hash/refs. Evidence: `uv run pytest -q orchestrator/tests/test_workflow.py web/backend/tests/test_memory.py web/backend/tests/test_control.py tests/test_opencode_audit.py` -> 25 passed; `uv run pytest -q tests/test_engine.py tests/test_loop_refs.py orchestrator/tests/test_workflow.py` -> 46 passed; `uv run pytest -q web/backend/tests/test_events.py web/backend/tests/test_memory.py` -> 7 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M08a provenance/scrubbing: added `memory_provenance()` as the compact packet future next-step/DWA generators should cite; memory search now scrubs query/room before CLI invocation and scrubs output before returning or caching `last-search.txt`. Evidence: `uv run pytest -q tests/test_memory_palace.py web/backend/tests/test_memory.py tests/test_opencode_audit.py orchestrator/tests/test_workflow.py` -> 23 passed; `uv run pytest -q web/backend/tests/test_intents.py tests/test_usage_events.py` -> 3 passed; `./web/frontend/build.sh` passed; `git diff --check` clean.
- 2026-04-22 M02a consumption: deterministic next-step packets now include `memory_provenance()` with wake-up hash and memory refs. Evidence tracked in `M02-intent-lifecycle-and-next-step.md`.
- 2026-04-22 M08 slice A: PWA memory surface landed. `EventEngine` now folds `memory_status`, `memory_refreshed`, `memory_search_completed`, and `memory_error` into replayable `memoryEvents` plus `memPalaceStatus`; scrub/replay rebuild uses the event-index state instead of current palace state. `SceneManager` adds tappable `memory-core:body` on the goal core, and `GameShell` adds `memory-core-control` / `memory-core-sheet` with status, wing, wake hash, packet size, wake-up preview, last search, recent memory event rail, and a sync button posting to `/api/projects/{id}/memory/sync`. Evidence: `uv run pytest -q web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py` -> 25 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,342,500 bytes; `git diff --check` clean.
- 2026-04-22 M08 slice B: cross-phase memory diff landed. `memory_diff` is registered in the backend/frontend event registries; `Orchestrator._emit_memory_diff_for_phase` runs after each successful `phase_done`, compares current `.orchestrator/memory/wake-up.md` hash to the prior phase-boundary hash, and emits `previous_wake_up_hash`, `wake_up_hash`, `wake_up_bytes`, `hash_changed`, `memory_refs`, `artifact_refs`, and source refs to the triggering phase event. `EventEngine` folds `memory_diff` into `memoryEvents`; `memoryStatusCard` displays changed/unchanged diff rows. Evidence: `uv run pytest -q tests/test_engine.py tests/test_event_schema.py web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py` -> 63 passed; `./web/frontend/build.sh` -> `dist/app.js` 1,342,965 bytes; `git diff --check` clean.
- 2026-04-22 M08 slice C: Story Lens memory claim provenance landed. Backend audit confirmed `narrative_digest_created`, `discussion_entry_created`, and `discussion_highlight_created` already carry `wake_up_hash` + `memory_refs`; `GameShell.storyDigestCard`, `discussionEntryCard`, and `discussionHighlightCard` now render memory refs and wake hash chips next to source/artifact refs so replayed claims show the memory packet that shaped them. Evidence: `uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_event_engine.py` -> 26 passed.
- 2026-04-22 M08 slice D1: role-wing contract and truthful cost accounting landed. `orchestrator.lib.memory_palace` now reserves deterministic role wings for architect/coder/tester/reviewer/narrator/deployer/judge, persists them into memory metadata, returns them from status/provenance, and records `cost_accounting.usage_recorded=false` because current MemPalace CLI calls expose no token/cost payload. `build_operator_context` injects the current phase's reserved role wing beside the deterministic wake-up packet. Memory events and the PWA memory card surface role wings plus the cost-accounting note. Evidence: `uv run pytest -q tests/test_memory_palace.py tests/test_intents.py orchestrator/tests/test_workflow.py web/backend/tests/test_memory.py web/frontend/tests/test_event_engine.py web/frontend/tests/test_game_map.py` -> 53 passed.
- 2026-04-22 M08 slice D2: default MemPalace MCP config landed. `orchestrator.lib.endpoints.MemoryMcpConfig` defaults to enabled for coder/tester/reviewer/narrator and parses `memory_mcp.enabled`, selected roles, command, timeout, and environment from YAML/env. `orchestrator.lib.opencode_config` emits local `mcp.mempalace` config by default, disables `mempalace_*` globally, and re-enables it per selected role. Architect/judge are rejected so zero-tool roles remain deterministic; `memory_mcp.enabled: false` removes MCP from generated config. Evidence: `uv run pytest -q tests/test_endpoints.py tests/test_opencode_config.py tests/test_cli_run.py tests/test_integration_h6_opencode_pipeline.py` -> 32 passed.
