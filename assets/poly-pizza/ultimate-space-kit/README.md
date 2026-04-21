# Ultimate Space Kit Inventory

Vendored GLB subset from Poly Pizza:

- Source: https://poly.pizza/bundle/Ultimate-Space-Kit-YWh743lqGX
- Creator: Quaternius
- License: CC0 1.0 Public Domain
- Download inspected: `https://static.poly.pizza/list/YWh743lqGX-glb-676332404.zip`
- Local manifest: `manifest.json`
- Local models: `models/*.glb`

## Why This Kit Matters

This pack is the first coherent model vocabulary for the zero-g orchestration
map. It includes actors, vehicles, loop bodies, facilities, connectors, tokens,
and blockers in one art direction.

Use it to model engine concepts:

| Engine concept | Model convention |
| --- | --- |
| Human/operator presence | Astronaut |
| Implementation/build worker | Mech |
| Test/CI/tool runner | Rover or round rover |
| Deployment/transfer | Spaceship |
| Review/gates/council | Geodesic dome, radar, astronaut reviewer |
| Memory/provider telemetry | Antenna, radar, solar panel |
| Loop body/cluster anchor | Planet variants |
| Task/artifact/status tokens | Pickup crate, key card, health, thunder, sphere |
| Reroute/dependency socket | Connector |
| Blocker/error/debris | Rocks or enemy actors |

## Animation Findings

The kit includes animated character GLBs:

- 3 Astronaut models, each with 18 animations.
- 4 Mech models, each with 17 animations.
- 3 Enemy models, with 8 to 14 animations.

Useful animation semantics:

- `Idle`: ready or observing.
- `Walk` / `Run`: active motion toward work.
- `Wave` / `Hello`: selected, summoned, or greeting.
- `Yes`: approved, accepted, resolved.
- `No`: rejected, invalid, blocked.
- `HitReact` / `HitRecieve_*`: failure, provider error, failed validation.
- `Death`: terminal failure only.
- `Pickup`: artifact or task consumption.
- `Shoot_*`: high-energy tool/action burst.

## Runtime Policy

- Do not preload this kit before first render.
- Do not instantiate all 87 models in one scene.
- Load a curated subset based on focused loop cluster and active engine events.
- On mobile, run full skeletal animation for only the focused actor.
- Keep lower-priority actors static or collapsed to motes/silhouettes.

## Inventory Summary

Generated from `manifest.json`:

- 87 GLB models.
- 11,361,152 bytes extracted.
- 3 operator astronaut models.
- 4 heavy-agent mech models.
- 3 tool-runner rover models.
- 4 transfer/deploy spaceship models.
- 11 loop-body planet models.
- 9 facility/cluster-anchor models.
- 7 status/artifact token models.
- 5 provider/telemetry facility models.
- 7 blocker/asteroid rock models.
- 1 connector model.
- 27 optional biome props.
