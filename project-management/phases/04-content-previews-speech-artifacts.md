# Phase 4 - Content Previews, Speech, And Artifacts

## Goal

Make generated work visible in the universe. A user should see who is creating
what, where it is going, what depends on it, and who is speaking to whom.

## Required Context

- `docs/spatial-flow-universe-design.md`
- `web/backend/routes/artifacts.py`
- `web/backend/routes/logs.py`
- `web/frontend/src/game/EventEngine.ts`
- `web/frontend/src/game/SceneManager.ts`
- `web/frontend/src/game/types.ts`

## Implementation Surface

- `web/frontend/src/game/content/ContentPreviewLayer.ts`
- `web/frontend/src/game/content/SpeechTailLayer.ts`
- `web/frontend/src/game/content/ArtifactAccretion.ts`
- `web/frontend/src/game/SceneManager.ts`
- backend artifact/log routes only if missing data blocks progress

## Task 4.1 - Define Content Event Contract

Status: Not started

Actions:

- Document and implement the minimum event fields needed for previews:
  - `artifact_refs`
  - `evidence_refs`
  - `memory_refs`
  - `source_atom_id`
  - `target_atom_id`
  - `summary`
  - `content_kind`
- Add inference fallback when fields are missing.
- Do not block rendering when artifacts cannot be fetched.

Acceptance:

- Preview system can run from current event history.
- Richer fields improve the view but are not mandatory.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_event_engine.py
```

## Task 4.2 - Implement ContentPreviewLayer

Status: Not started

Actions:

- Add DOM/WebGL hybrid world labels.
- Pool DOM elements.
- Project world anchors to screen coordinates.
- Support far/mid/near LOD:
  - far: colored patch/glyph,
  - mid: title plus two or three lines,
  - near: readable excerpt/diff/test summary.
- Collapse labels by priority before overlap.

Acceptance:

- Selected atom/artifact can show a readable preview.
- Non-selected atoms do not flood the screen.
- Mobile shows at most one primary readable preview per focused cluster.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 4.3 - Implement ArtifactAccretion

Status: Not started

Actions:

- Create artifact bodies near producing atoms.
- Lifecycle:
  - seed,
  - draft,
  - review,
  - final,
  - rework.
- Map content type to shape:
  - code crystal,
  - prose slab,
  - plan prism,
  - test verdict capsule,
  - deployment satellite.
- Show artifact transfer between clusters.

Acceptance:

- Work-in-progress reads as a forming object, not a progress bar.
- Rejected/repaired artifacts visibly crack and re-accrete.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Task 4.4 - Implement SpeechTailLayer

Status: Not started

Actions:

- Render recent messages as directional comet-like text ribbons.
- Anchor speech to speaker and recipient when known.
- Collapse older speech into replay markers.
- Add bottom "now" strip only as a peripheral mobile affordance.

Acceptance:

- User can see direction of communication without arrows.
- Speech does not become a wall of chat boxes.
- Selecting a speech tail opens underlying event detail.

Evidence:

```bash
uv run pytest -q web/frontend/tests/test_game_map.py
./web/frontend/build.sh
```

## Phase Exit Criteria

- Content previews are visible and LOD-managed.
- Artifacts form, transfer, stabilize, and repair in-world.
- Speech tails show who spoke to whom.
- Mobile remains readable and uncluttered.
