"""AssetManager fixture tests."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MANAGER_TS = ROOT / "web" / "frontend" / "src" / "game" / "assets" / "AssetManager.ts"
MANIFEST_TS = ROOT / "web" / "frontend" / "src" / "game" / "assets" / "manifest.ts"


def run_asset_script(tmp_path: Path, entry: Path, script: str) -> None:
    bundle = tmp_path / "asset-module.mjs"
    subprocess.run(
        [
            "npx",
            "--yes",
            "esbuild@0.24.0",
            str(entry),
            "--bundle",
            "--format=esm",
            "--platform=node",
            "--target=es2020",
            f"--outfile={bundle}",
            "--log-level=warning",
        ],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["node", "--input-type=module", "-e", textwrap.dedent(script).replace("__BUNDLE__", bundle.as_posix())],
        cwd=ROOT,
        check=True,
    )


def test_manifest_excludes_reference_and_hdri_from_core(tmp_path: Path) -> None:
    run_asset_script(
        tmp_path,
        MANIFEST_TS,
        """
        import assert from 'node:assert/strict';
        import { CORE_GAME_ASSETS, DEFERRED_GAME_ASSETS, REFERENCE_ASSETS, SERVICE_WORKER_ASSET_PATHS } from '__BUNDLE__';

        assert.equal(REFERENCE_ASSETS.lensDirt, '/assets/post-processing-refs/lensDirt1.png');
        assert.equal(CORE_GAME_ASSETS.some((asset) => asset.path === REFERENCE_ASSETS.lensDirt), false);
        assert.equal(CORE_GAME_ASSETS.some((asset) => asset.path.includes('/hdris/')), false);
        assert.equal(DEFERRED_GAME_ASSETS.some((asset) => asset.id === 'environment.hdriSky'), true);
        assert.equal(DEFERRED_GAME_ASSETS.some((asset) => asset.id === 'polyPizza.planetA' && asset.kind === 'model'), true);
        assert.equal(SERVICE_WORKER_ASSET_PATHS.includes(REFERENCE_ASSETS.lensDirt), false);
        assert.equal(SERVICE_WORKER_ASSET_PATHS.some((path) => path.includes('/hdris/')), false);
        assert.equal(SERVICE_WORKER_ASSET_PATHS.some((path) => path.includes('/poly-pizza/')), false);
        """,
    )


def test_asset_manager_loads_core_and_uses_optional_placeholder(tmp_path: Path) -> None:
    run_asset_script(
        tmp_path,
        MANAGER_TS,
        """
        import assert from 'node:assert/strict';
        import { AssetManager } from '__BUNDLE__';

        const requested = [];
        globalThis.URL.createObjectURL = () => `blob:${requested.length}`;
        globalThis.URL.revokeObjectURL = () => {};
        globalThis.fetch = async (path) => {
          requested.push(String(path));
          if (String(path).includes('optional-missing')) {
            return { ok: false, status: 404, statusText: 'Not Found' };
          }
          return {
            ok: true,
            blob: async () => new Blob(['ok'], { type: 'application/octet-stream' }),
          };
        };

        const manager = new AssetManager([
          { id: 'core.hex', path: '/assets/environments/hex-grid.png', kind: 'texture', phase: 'core', optional: false, bytesHint: 1 },
          { id: 'deferred.optional', path: '/assets/optional-missing.png', kind: 'texture', phase: 'deferred', optional: true, bytesHint: 1 },
          { id: 'reference.lensDirt', path: '/assets/post-processing-refs/lensDirt1.png', kind: 'texture', phase: 'reference', optional: true, bytesHint: 1 },
        ]);

        const progress = [];
        manager.onProgress((item) => progress.push(item));
        const core = await manager.preloadCore();
        assert.equal(core.length, 1);
        assert.equal(core[0].status, 'loaded');
        assert.deepEqual(requested, ['/assets/environments/hex-grid.png']);

        const optional = await manager.load('deferred.optional');
        assert.equal(optional.status, 'placeholder');
        assert.equal(optional.blob.type, 'image/png');
        assert.equal(requested.includes('/assets/post-processing-refs/lensDirt1.png'), false);
        await assert.rejects(() => manager.load('reference.lensDirt'), /Reference-only asset/);
        assert.equal(progress.at(-1).loaded, 1);
        """,
    )
