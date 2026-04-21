"""Three.js map route fixture tests."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
LAYOUT_TS = ROOT / "web" / "frontend" / "src" / "game" / "layout.ts"
GAME_SHELL_TS = ROOT / "web" / "frontend" / "src" / "game" / "GameShell.ts"
FLOW_TYPES_TS = ROOT / "web" / "frontend" / "src" / "game" / "flows" / "FlowTypes.ts"
FLOW_PATH_TS = ROOT / "web" / "frontend" / "src" / "game" / "flows" / "FlowPath.ts"
FLOW_DIRECTOR_TS = ROOT / "web" / "frontend" / "src" / "game" / "flows" / "FlowDirector.ts"


def run_script(tmp_path: Path, entry: Path, script: str, include_three: bool = False) -> None:
    bundle = tmp_path / "module.mjs"
    if include_three:
        subprocess.run(
            ["npm", "install", "--prefix", str(ROOT / "web" / "frontend"), "--no-package-lock", "--no-save"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    command = [
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
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    subprocess.run(
        ["node", "--input-type=module", "-e", textwrap.dedent(script).replace("__BUNDLE__", bundle.as_posix())],
        cwd=ROOT,
        check=True,
    )


def test_workflow_layout_builds_floating_graph(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        LAYOUT_TS,
        """
        import assert from 'node:assert/strict';
        import { layoutWorkflowAtoms } from '__BUNDLE__';

        const layout = layoutWorkflowAtoms([
          { id: 'discover', title: 'Discover', type: 'phase', handler: 'discover', enabled: true },
          { id: 'build', title: 'Build', type: 'phase', handler: 'build', enabled: true },
          { id: 'ship', title: 'Ship', type: 'phase', handler: 'ship', enabled: false },
        ]);

        assert.deepEqual(layout.nodes.map((node) => node.id), ['discover', 'build', 'ship']);
        assert.equal(new Set(layout.nodes.map((node) => node.x)).size > 1, true);
        assert.equal(new Set(layout.nodes.map((node) => node.z)).size > 1, true);
        assert.deepEqual(layout.edges.map((edge) => edge.id), ['discover->build', 'build->ship']);
        assert.equal(layout.loops.some((loop) => loop.id === 'core_loop'), true);
        assert.equal(typeof layout.bounds.center.x, 'number');
        assert.equal(layout.bounds.radius > 4, true);
        assert.equal('cells' in layout, false);
        assert.equal('q' in layout.nodes[0], false);
        """,
    )


def test_known_workflow_uses_lattice_slots(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        LAYOUT_TS,
        """
        import assert from 'node:assert/strict';
        import { layoutWorkflowAtoms } from '__BUNDLE__';

        const layout = layoutWorkflowAtoms([
          { id: 'memory_refresh', title: 'Memory', type: 'phase', handler: 'memory_refresh', enabled: true },
          { id: 'persona_forum', title: 'Team', type: 'phase', handler: 'persona_forum', enabled: true },
          { id: 'architect', title: 'Architect', type: 'phase', handler: 'architect', enabled: true },
          { id: 'approve_sprint_plan', title: 'Approve', type: 'gate', handler: 'approve', enabled: true },
          { id: 'implementation', title: 'Build', type: 'phase', handler: 'implementation', enabled: true },
          { id: 'testing', title: 'Verify', type: 'phase', handler: 'testing', enabled: true },
          { id: 'approve_review', title: 'Review Gate', type: 'gate', handler: 'approve_review', enabled: true },
        ]);

        const byId = Object.fromEntries(layout.nodes.map((node) => [node.id, node]));
        assert.equal(byId.memory_refresh.loopId, 'memory_loop');
        assert.equal(byId.architect.loopId, 'core_loop');
        assert.equal(byId.approve_review.loopId, 'escalation_loop');
        assert.equal(byId.approve_sprint_plan.lane, 'gate');
        assert.equal(byId.approve_review.lane, 'gate');
        assert.equal(layout.edges.some((edge) => edge.from === 'approve_sprint_plan' && edge.to === 'testing'), true);
        assert.equal(layout.loops.length >= 3, true);
        assert.equal(layout.bounds.radius <= 10, true);
        for (let i = 0; i < layout.nodes.length; i += 1) {
          for (let j = i + 1; j < layout.nodes.length; j += 1) {
            const a = layout.nodes[i];
            const b = layout.nodes[j];
            const distance = Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
            assert.equal(distance > 0.4, true);
          }
        }
        """,
    )


def test_webgl_detection_uses_canvas_context(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';
        import { canUseWebGL } from '__BUNDLE__';

        globalThis.document = {
          createElement: () => ({ getContext: (name) => name === 'webgl2' ? ({}) : null }),
        };
        assert.equal(canUseWebGL(), true);

        globalThis.document = {
          createElement: () => ({ getContext: () => null }),
        };
        assert.equal(canUseWebGL(), false);
        """,
        include_three=True,
    )


def test_flow_types_are_pure_and_mode_driven(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        FLOW_TYPES_TS,
        """
        import assert from 'node:assert/strict';
        import { flowKindColor, flowModeOpacity, flowModeRadiusMultiplier } from '__BUNDLE__';

        assert.equal(typeof flowKindColor('intent'), 'number');
        assert.equal(flowModeOpacity('active') > flowModeOpacity('idle'), true);
        assert.equal(flowModeRadiusMultiplier('selected') > flowModeRadiusMultiplier('idle'), true);
        """,
    )


def test_flow_path_exposes_curve_helpers(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        FLOW_PATH_TS,
        """
        import assert from 'node:assert/strict';
        import { createRequire } from 'node:module';
        import { FlowPath } from '__BUNDLE__';

        const require = createRequire(new URL('./web/frontend/package.json', `file://${process.cwd()}/`));
        const THREE = require('three');
        const path = new FlowPath({
          id: 'a->b',
          from: new THREE.Vector3(0, 0, 0),
          to: new THREE.Vector3(2, 0, 0),
          kind: 'intent',
          mode: 'queued',
        });
        const mid = path.pointAt(0.5);
        const tangent = path.tangentAt(0.5);
        assert.equal(mid.y > 0, true);
        assert.equal(tangent.length() > 0.5, true);
        assert.equal(path.mesh.userData.flowPathId, 'a->b');
        path.setMode('selected', 'repair');
        assert.equal(path.mesh.userData.flowKind, 'repair');
        path.dispose();
        """,
        include_three=True,
    )


def test_flow_director_maps_events_to_commands(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        FLOW_DIRECTOR_TS,
        """
        import assert from 'node:assert/strict';
        import { commandsForRunEvent } from '__BUNDLE__';

        const layout = {
          nodes: [
            { id: 'architect', lane: 'plan' },
            { id: 'implementation', lane: 'build' },
            { id: 'testing', lane: 'verify' },
          ],
          edges: [
            { id: 'architect->implementation', from: 'architect', to: 'implementation', kind: 'sequence' },
            { id: 'implementation->testing', from: 'implementation', to: 'testing', kind: 'sequence' },
          ],
          loops: [],
          bounds: { center: { x: 0, y: 0, z: 0 }, radius: 4 },
        };
        const snapshot = { live: true, replayIndex: -1 };

        assert.deepEqual(
          commandsForRunEvent({ type: 'phase_start', step: 'implementation', event_id: 'evt1' }, layout, snapshot).map((item) => item.type),
          ['path_mode', 'pulse'],
        );
        const usage = commandsForRunEvent({ type: 'usage_recorded', atom_id: 'implementation', event_id: 'evt2' }, layout, snapshot);
        assert.equal(usage.some((item) => item.type === 'dust' && item.kind === 'cost'), true);
        const intent = commandsForRunEvent({ type: 'operator_intent', atom_id: 'testing', event_id: 'evt3' }, layout, snapshot);
        assert.equal(intent.some((item) => item.type === 'pulse' && item.kind === 'intent'), true);
        """,
    )


def test_game_shell_bundle_contains_replay_surface(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';
        import { canUseWebGL } from '__BUNDLE__';

        assert.equal(typeof canUseWebGL, 'function');
        """,
        include_three=True,
    )
    bundle = tmp_path / "module.mjs"
    text = bundle.read_text()
    assert "byAtom" in text
    assert "bottom-chip-cluster" in text
    assert "radial-action-ring" in text
    assert "compose-dock" in text
    assert "timeline-ribbon" in text
    assert "data-view-level" in text
    assert "setViewLevel" in text
    assert "<select" not in text
    assert "/intents" in text
