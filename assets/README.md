# PWA Visual Assets

Vendored assets for the Three.js/PWA visual system. These are small runtime assets except for the optional post-processing reference texture.

## Build Map

Use this as the asset handoff for the first PWA scene implementation.

| System | Runtime assets | Intent |
| --- | --- | --- |
| Scene environment | `environments/hex-grid.png`, `hdris/kloppenheim-02-puresky-1k.hdr` | Ground the scene with a quiet hex substrate and low-frequency night-sky image-based lighting. |
| Atom nodes and gate crystals | `atom-meshes/flat-normal.png`, `atom-meshes/canvas-grain.png` | Keep bevels and facets clean while adding a restrained material grain to node platforms. |
| Atom and artifact badges | `icon-sprites/tabler-icons.woff2` | Provide a consistent technical outline icon language for type badges, controls, and artifact marks. |
| Edges and event particles | `edge-particle-sprites/disc.png`, `edge-particle-sprites/spark1.png` | Drive travelling edge pulses with the soft disc and richer event bursts with the spark sprite. |
| Memory palace arc | `mempalace/radial-alpha-gradient.png`, `mempalace/lensflare0.png` | Shape soft translucent arc masks and memory-orb highlights. |
| Artifact cards | `artifact-textures/canvas-grain.png`, `icon-sprites/tabler-icons.woff2` | Give crystallized output cards subtle paper tooth and icon consistency with atom badges. |
| Typography | `fonts/InterVariable.woff2`, `fonts/JetBrainsMono-Regular.woff2` | Use Inter for UI labels/HUD numerics and JetBrains Mono for event streams or JSONL-style readouts. |
| Post-processing reference | `post-processing-refs/lensDirt1.png` | Reference or source texture for bloom dirt; downscale before shipping as a runtime mobile asset. |

## Runtime Notes

- Prefer loading PNG/WOFF2/HDR assets through the PWA bundler or static public asset path rather than hotlinking upstream sources.
- Treat `post-processing-refs/lensDirt1.png` as reference material until it is resized or compressed for the actual bloom pass.
- The two `canvas-grain.png` copies are intentionally duplicated by consumer folder so atom materials and artifact materials can evolve independently.
- Keep the source URLs and licenses below when moving or optimizing these assets.
- The implementation contract is defined in `docs/threejs-asset-pipeline.md`.
- Phase 1 must not load `post-processing-refs/lensDirt1.png` at runtime.
- HDRI loading should happen after first render until mobile profiling proves it is safe to include in the first-frame payload.

## Runtime Budget

Initial mobile target:

| Budget | Target |
| --- | --- |
| Runtime asset payload before first scene render | Under 2 MB, excluding fonts already cached |
| First render after app shell | Under 2 seconds on simulated mid-range Android |
| Texture count before first frame | 8 or fewer |
| Reference-only assets | 0 loaded at runtime |

If implementation exceeds these numbers, the app must degrade by delaying HDRI,
post-processing, and rich burst particles before it delays atom map rendering.

## Inventory

| Path | Role | Source | License | Notes |
| --- | --- | --- | --- | --- |
| `environments/hex-grid.png` | Environment substrate | https://github.com/mpalmerlee/HexagonTools/blob/master/HexGrid.png | MIT per repo README | 400x300 PNG. GitHub license API does not expose a root SPDX license file. |
| `atom-meshes/flat-normal.png` | Atom/gate normal baseline | https://github.com/meetar/three.js-normal-map-0/blob/master/flat.png | MIT | 265x265 PNG. |
| `atom-meshes/canvas-grain.png` | Atom surface grain | https://github.com/stamen/splatter/blob/master/canvas.png | MIT | 256x256 PNG. |
| `artifact-textures/canvas-grain.png` | Artifact card grain | https://github.com/stamen/splatter/blob/master/canvas.png | MIT | Duplicate of `atom-meshes/canvas-grain.png` kept for clear consumer ownership. |
| `icon-sprites/tabler-icons.woff2` | Atom and artifact icon font | https://tabler.io/icons | MIT | Tabler Icons webfont v3.33.0. |
| `edge-particle-sprites/disc.png` | Edge pulse sprite | https://github.com/mrdoob/three.js/blob/dev/examples/textures/sprites/disc.png | MIT | 32x32 PNG. |
| `edge-particle-sprites/spark1.png` | Event burst sprite | https://github.com/mrdoob/three.js/blob/dev/examples/textures/sprites/spark1.png | MIT | 32x32 PNG. |
| `mempalace/radial-alpha-gradient.png` | Memory arc alpha mask | https://github.com/stamen/splatter/blob/master/radial-alpha-gradient.png | MIT | 255x255 PNG. |
| `mempalace/lensflare0.png` | Memory orb glow sprite | https://github.com/mrdoob/three.js/blob/dev/examples/textures/lensflare/lensflare0.png | MIT | 512x512 PNG. |
| `hdris/kloppenheim-02-puresky-1k.hdr` | Runtime environment lighting | https://polyhaven.com/a/kloppenheim_02_puresky | CC0 | 1K HDR from Poly Haven. |
| `fonts/InterVariable.woff2` | UI typography | https://github.com/rsms/inter | OFL-1.1 | Variable font. |
| `fonts/JetBrainsMono-Regular.woff2` | Event/code readouts | https://github.com/JetBrains/JetBrainsMono | OFL-1.1 | Regular mono font. |
| `post-processing-refs/lensDirt1.png` | Bloom/dirt reference texture | https://github.com/sonicether/SE-Natural-Bloom-Dirty-Lens/blob/master/Assets/SE%20Natural%20Bloom/Lens%20Textures/lensDirt1.png | MIT | 1920x1080 PNG, about 3 MB. Consider downscaling before runtime use. |

## Manual References

| Reference | Source | License | Notes |
| --- | --- | --- | --- |
| BloomEffect docs | https://pmndrs.github.io/postprocessing/public/docs/class/src/effects/BloomEffect.js~BloomEffect.html | Zlib | Reference only; `pmndrs/postprocessing` is Zlib licensed, not MIT. |
| Kloppenheim 02 Pure Sky | https://polyhaven.com/a/kloppenheim_02_puresky | CC0 | Runtime 1K HDR is vendored under `hdris/`. |
| SE Natural Bloom lens dirt | https://github.com/sonicether/SE-Natural-Bloom-Dirty-Lens/blob/master/Assets/SE%20Natural%20Bloom/Lens%20Textures/lensDirt1.png | MIT | Vendored as `post-processing-refs/lensDirt1.png`. |
