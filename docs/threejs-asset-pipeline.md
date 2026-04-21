# Three.js Asset Pipeline

## Purpose

The Three.js client must use the vendored visual assets as a runtime design
system, not as optional decoration. The asset kit turns the orchestration map
from generic geometry into a coherent product surface.

Asset inventory and license sources live in `assets/README.md`.

## AssetManager Contract

`AssetManager` is the single loader and cache for runtime visual assets.

Responsibilities:

- Load PNG, WOFF2, and HDR assets from the PWA static asset path.
- Cache loaded `Texture`, `DataTexture`, font, and icon metadata instances.
- Expose a typed manifest so scene code does not hard-code paths.
- Provide placeholder textures when optional assets fail.
- Track load progress for the PWA loading state.
- Never hotlink upstream asset URLs at runtime.

Proposed file:

```text
web/frontend/src/game/assets/AssetManager.ts
```

## Runtime Manifest

The first implementation should expose this manifest:

```typescript
export interface GameAssetManifest {
  environment: {
    hexGrid: string
    hdriSky: string
  }
  atom: {
    flatNormal: string
    grain: string
  }
  artifact: {
    grain: string
  }
  particles: {
    disc: string
    spark: string
  }
  memPalace: {
    radialAlpha: string
    lensflare: string
  }
  fonts: {
    inter: string
    jetbrainsMono: string
    tablerIcons: string
  }
}
```

## Asset Use By Scene System

### Scene Environment

- Use `assets/environments/hex-grid.png` as the ground-plane substrate.
- Use `assets/hdris/kloppenheim-02-puresky-1k.hdr` for image-based lighting
  only after mobile memory budget is measured.
- Fallback: dark material with procedural grid lines.

### Atom Nodes And Gates

- Use `assets/atom-meshes/flat-normal.png` as baseline normal data.
- Use `assets/atom-meshes/canvas-grain.png` as restrained material grain.
- Do not let texture contrast overpower state color. State readability wins.

### Badges And Icons

- Use `assets/icon-sprites/tabler-icons.woff2`.
- Render icon glyphs into canvas textures for atom badges, artifact cards, and
  HUD controls.
- Keep icon mapping centralized. Scene code should request semantic icon ids,
  not glyph code points directly.

### Events And Edges

- Use `assets/edge-particle-sprites/disc.png` for travelling edge pulses.
- Use `assets/edge-particle-sprites/spark1.png` for bursts on completion,
  errors, gate decisions, and repair cycles.
- Particle color still comes from event type; sprite texture supplies shape.

### MemPalace

- Use `assets/mempalace/radial-alpha-gradient.png` as the arc alpha mask.
- Use `assets/mempalace/lensflare0.png` for memory orb highlights.
- Memory assets must stay secondary to atom state. Avoid full-screen flare.

### Artifact Cards

- Use `assets/artifact-textures/canvas-grain.png` on artifact cards.
- Use Tabler icons for artifact type marks.
- Artifact text remains DOM-rendered in FocusPanel, not canvas text.

### Typography

- Use `assets/fonts/InterVariable.woff2` for HUD, labels, and panels.
- Use `assets/fonts/JetBrainsMono-Regular.woff2` for event streams, JSONL,
  call ids, token/cost counters, and llama.cpp telemetry.

### Post Processing

- `assets/post-processing-refs/lensDirt1.png` is reference-only until a
  mobile-sized runtime derivative is generated.
- Do not ship the full 1920x1080 dirt texture in the initial mobile runtime.
- First implementation uses CSS brightness fallback as specified in the
  roadmap. True bloom waits for measured performance.

## Mobile Budgets

Initial runtime budget targets:

- First scene asset payload, excluding fonts already cached: under 2 MB.
- First render after app shell: under 2 seconds on simulated mid-range Android.
- Texture count before first frame: 8 or fewer.
- HDR loading may happen after the first frame.
- Post-processing reference assets are excluded from runtime cache by default.

If the budget is exceeded, load order is:

1. DOM shell and fonts.
2. EventEngine history.
3. Hex grid, atom grain, particle disc.
4. Atom map first render.
5. MemPalace lensflare and artifact grain.
6. HDRI and optional richer particles.

## Offline Cache Policy

The service worker should precache only runtime-critical assets:

- `hex-grid.png`
- `flat-normal.png`
- atom and artifact grain PNGs
- `disc.png`
- `radial-alpha-gradient.png`
- Inter and JetBrains Mono fonts
- Tabler icon font

The service worker should not precache:

- `post-processing-refs/lensDirt1.png`
- HDRI until mobile profiling confirms it is acceptable

## Acceptance Criteria

- The first Three.js scene uses vendored assets, not procedural placeholders
  except for fallback paths.
- Asset paths are centralized in one manifest.
- Runtime does not hotlink upstream sources.
- Reference-only assets are not loaded in Phase 1.
- Missing optional textures degrade gracefully.
- Asset loading state is visible in the PWA.
- Licenses and upstream sources remain documented in `assets/README.md`.
