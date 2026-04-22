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
- [ ] Add next-step / DWA memory refs so the narrative surface can cite the wake-up packet and relevant searches. Partial 2026-04-22: M02a next-step packets include `memory_provenance()`; DWA/narrative digest refs remain pending until M04/M05.
- [ ] PWA: memory body (radar/antenna prop) orbits the goal core; tap opens memory panel (status, last search, sync control, wake-up preview).
- [ ] Memory diffing hook: before/after each phase emits a memory diff summary event (future-capable; minimum: hash changed flag).
- [ ] Agent-specific wings: each SDLC role gets a wing scoped to its concerns (can be stubbed with empty wings v1).
- [ ] Optional after provenance is green: generate OpenCode `mcp.mempalace` config using `python -m mempalace.mcp_server`, disabled globally and enabled only for selected tool-using agents.

## Quality gates

- [x] G1 Event integrity on memory events.
- [x] G8 Security — search queries scrubbed; no secrets in `last-search.txt`.
- [ ] G7 Cost — memory operations emit `usage_recorded` where they invoke models (e.g., embedding).
- [ ] G4 No-dashboard — memory surface is a body + panel, not a tab grid.
- [ ] G5 Source-ref credibility — every memory-backed narrative/DWA claim carries a memory/artifact/event ref.
- [ ] G2 Replay determinism — replay uses the wake-up hash/refs known at that event index, not current memory state.

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
- [ ] Next-step / DWA packets carry memory refs so the PWA can display memory provenance. Partial 2026-04-22: next-step packets carry memory refs; DWA packets do not exist yet.
- [ ] PWA shows memory status, last search, sync button, wake-up preview.
- [x] Memory errors appear as events (not as silent warnings).
- [ ] Hash changes across phases produce at least a `memory_refreshed` with diff summary.
- [ ] Optional M08b only: generated opencode config can expose MemPalace MCP to selected tool-enabled agents without enabling it for zero-tool roles by accident.

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
