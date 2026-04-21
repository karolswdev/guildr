# Poly Pizza Model Pack

Downloaded from https://poly.pizza/search/planet on 2026-04-21 as a starter
library for the zero-g orchestration map.

The backend serves this folder at `/assets/poly-pizza/...`. These models should
be treated as deferred scene assets, not first-frame core assets.

The `ultimate-space-kit/` subfolder is a separate CC0 Quaternius bundle that
should become the semantic actor/model vocabulary for the orchestration map:
astronauts for operator/review presence, mechs for implementation workers,
rovers for testing/tool runners, spaceships for deployment/transfer, planets
for loop bodies, and pickups/connectors/facilities for artifacts, gates, and
telemetry. See `ultimate-space-kit/README.md` and
`ultimate-space-kit/manifest.json`.

## Inventory

| Model | Title | Creator | License | Size | Source |
| --- | --- | --- | --- | ---: | --- |
| `planet-18Uxrb2dIc/planet-18Uxrb2dIc.glb` | Planet | Quaternius | CC0 1.0 | 84 KB | https://poly.pizza/m/18Uxrb2dIc |
| `planet-9g1aIbfR9Y/planet-9g1aIbfR9Y.glb` | Planet | Quaternius | CC0 1.0 | 72 KB | https://poly.pizza/m/9g1aIbfR9Y |
| `planet-IVnmauIgWX/planet-IVnmauIgWX.glb` | Planet | Quaternius | CC0 1.0 | 57 KB | https://poly.pizza/m/IVnmauIgWX |
| `planet-5zzi8WUMXj/planet-5zzi8WUMXj.glb` | Planet | Quaternius | CC0 1.0 | 44 KB | https://poly.pizza/m/5zzi8WUMXj |
| `planet-rYguWNNPvA/planet-rYguWNNPvA.glb` | Planet | Quaternius | CC0 1.0 | 276 KB | https://poly.pizza/m/rYguWNNPvA |
| `planet-hKZtOOMadH/planet-hKZtOOMadH.glb` | Planet | Quaternius | CC0 1.0 | 87 KB | https://poly.pizza/m/hKZtOOMadH |
| `planet-B7xd3SZq0z/planet-B7xd3SZq0z.glb` | Planet | Quaternius | CC0 1.0 | 276 KB | https://poly.pizza/m/B7xd3SZq0z |
| `planet-pHZz4EMvVM/planet-pHZz4EMvVM.glb` | Planet | Quaternius | CC0 1.0 | 64 KB | https://poly.pizza/m/pHZz4EMvVM |
| `planet-4NxxeyYMPJ/planet-4NxxeyYMPJ.glb` | Planet | Quaternius | CC0 1.0 | 71 KB | https://poly.pizza/m/4NxxeyYMPJ |
| `pixel-planet-wise-0855-0714-KcQcdI9GTt/pixel-planet-wise-0855-0714-KcQcdI9GTt.glb` | Pixel Planet WISE 0855-0714 | AstroJar | CC0 1.0 | 103 KB | https://poly.pizza/m/KcQcdI9GTt |
| `planets-3_tN7i962hZ/planets-3_tN7i962hZ.glb` | Planets | Poly by Google | CC-BY 3.0 | 2670 KB | https://poly.pizza/m/3_tN7i962hZ |
| `asteroid-enaIlQWET9a/asteroid-enaIlQWET9a.glb` | Asteroid | Poly by Google | CC-BY 3.0 | 717 KB | https://poly.pizza/m/enaIlQWET9a |
| `space-probe-fnFCCFiHbQt/space-probe-fnFCCFiHbQt.glb` | Space probe | Poly by Google | CC-BY 3.0 | 2058 KB | https://poly.pizza/m/fnFCCFiHbQt |
| `satellite-orbiting-earth-4E2HTzh1DFQ/satellite-orbiting-earth-4E2HTzh1DFQ.glb` | Satellite orbiting Earth | Poly by Google | CC-BY 3.0 | 56 KB | https://poly.pizza/m/4E2HTzh1DFQ |

## Runtime Guidance

- Prefer the CC0 models for first integration experiments.
- The CC-BY 3.0 models can be used, but any published UI needs attribution for
  the title, creator, license, and source URL.
- Keep `manifest.json` as the machine-readable inventory; each model directory
  also has `metadata.json`.
- Keep `ultimate-space-kit/manifest.json` as the machine-readable inventory for
  the 87-model Quaternius kit.
- Do not add the whole pack to service-worker precache. Load selected models
  after first render or behind a feature flag.
