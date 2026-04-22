# M06 — PWA Lenses And Game-Grade Map Surface

## Purpose

Assemble Mythos, Recent Story, Next-Step, and Discussion into a single tactical map. Implement Global, Object, and Story Views as lenses over the same scene — not separate routes. Ship the first viewport that answers what/who/what-just-happened/what-next/where-to-intervene on iPhone portrait.
Narrator output should enter this surface as a visually JRPG-inspired dialogue layer over the map before it expands into deeper Story Cards. That is a UI treatment, not a requirement that the model roleplay a JRPG narrator.

## Why this phase exists

This is where the system stops feeling like a dashboard and starts feeling like a command surface. Design doc §Default PWA Screen + §Visual Grammar + §Target First-Viewport Experience. SRS §9 Mission Control. It depends on M01–M05 for content and M07 for artifact anchoring.

## Required context files

- `docs/pwa-narrative-replay-and-intervention-design.md` §Target First-Viewport Experience, §Default PWA Screen, §Visual Grammar
- `docs/spatial-flow-universe-design.md`
- `docs/ux-interaction-model.md`
- `../DIRECTION_GUARDRAILS.md`
- `web/frontend/src/scene/SceneManager.ts` and `GameShell`
- `QUALITY_GATES.md` G3, G4, G9

## Implementation surface

- `web/frontend/src/ui/lenses/{GlobalView,ObjectView,StoryView}.ts`
- `web/frontend/src/scene/bodies/{GoalCore,Persona,DwaSatellite,IntentPacket,NextStepBeam}.ts`
- `web/frontend/src/ui/HUD.tsx` (bottom HUD + top safe-area)
- `web/frontend/src/ui/sheets/{NextStepSheet,MythosSheet,PersonaMindSheet,StoryCard}.tsx`
- AssetManager — load GLBs progressively, never precache the kit

## Tasks

- [x] Goal Core body: calm glow, low-frequency pulse, tap → project brief sheet.
- [ ] Founding Team cluster: personas orbit discovery/plan region; selectable; speech tails on recent statements.
- [ ] Next-Step Beam: single highlighted corridor from last completed → next slated atom.
- [ ] Intent Packet visual: spawns at operator avatar/edge → travels to target atom; queued → applied/ignored/superseded states.
- [ ] DWA Story Satellites: latest bright, older fade into trail; thin tethers to source events/artifacts.
- [x] HUD: `Next: <step> · Story: <count> · Cost: <run> · Loop dots`.
- [x] Lens toggle: Global / Object / Story. Not routes — scene mutations. First pass uses Run / Loop / Object / Story controls over the same scene.
- [x] Object View: focus atom, float in/out bodies, bottom sheet (what / consumed / produced / next).
- [x] Story View first pass: focus camera on recent path, dim unrelated atoms, browse digest cards/source refs/discussion without route reload.
- [ ] Story View digest scrubber: timeline scrubs digests/story cards, not only raw events.
- [x] Narrator Dialogue: distinctive summary box, typewriter reveal, skip/replay, source affordance, reduced-motion fallback.
- [ ] Mobile portrait as default device target; test at 375×812.
- [ ] Semantic Space Kit use: astronaut=operator, mech=builder, rover=CI, spaceship=deploy, planets=loop bodies, radar/antenna/solar=memory/providers/budget.
- [ ] Replay/Live toggle in top safe-area; lens selection preserved across toggle.
- [ ] DOM overlay pool + collision manager so labels never overlap.

## Quality gates

- [ ] G3 Mobile usability — first viewport answers the five questions on iPhone portrait.
- [ ] G4 No-dashboard-regression — no new tab/card grid; loops read as gravitational clusters.
- [ ] G9 Accessibility — keyboard fallback for every map action; motion-reduce respected.
- [ ] DIRECTION_GUARDRAILS review gate captures (mobile portrait, desktop wide, selected atom, active flow, blocked/repair state, at least one deferred model loaded, no-overlap state).

## Evidence commands / checks

```bash
./web/frontend/build.sh
uv run pytest -q web/frontend/tests/test_game_map.py web/frontend/tests/test_lenses.py web/frontend/tests/test_hud.py
# manual: screenshots for each of the six review-gate captures, stored under project-management/evidence/M06/
```

## Done means

- [ ] First viewport on iPhone portrait shows goal + founding team + last step + next step + one DWA + HUD with next/story/cost.
- [ ] Tapping next atom opens Next-Step Sheet with composer.
- [ ] Tapping a persona opens Mind Sheet with stance composer.
- [ ] Tapping a DWA opens a Story Card with source refs.
- [ ] All three lenses operate on the same scene; no route reload.
- [ ] Six direction-guardrail captures collected and linked from STATUS evidence row.
- [ ] No kit GLB appears in `sw.js` precache (existing test still green).

## Known traps

- Introducing a second scene root per lens breaks motion continuity and intent-packet trajectories. Lenses mutate; they don't re-instantiate.
- Label overlap is the fastest dashboard-regression: collision-manage DOM overlays, not transform hacks.
- Story View collapsing into a full-screen modal is a dashboard relapse — keep the map visible, just dim and scrub.
- Narrator output as a plain stats card is a dashboard relapse — make the UI feel like an in-world dialogue surface, while keeping the model voice neutral and summary-oriented.
- Loading all 87 Space Kit GLBs on first render — guarded by `test_ultimate_space_kit_manifest.py`; don't break it.

## Handoff notes

- Feeds M11 (replay resilience) for scrubber + loop-stage band visuals.
- Any new HUD glyph must map to an existing quality question (see DIRECTION_GUARDRAILS).
