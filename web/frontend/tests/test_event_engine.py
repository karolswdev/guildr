"""EventEngine replay fixture tests."""

from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ENGINE_TS = ROOT / "web" / "frontend" / "src" / "game" / "EventEngine.ts"


def run_engine_script(tmp_path: Path, script: str) -> None:
    bundle = tmp_path / "event-engine.mjs"
    subprocess.run(
        [
            "npx",
            "--yes",
            "esbuild@0.24.0",
            str(ENGINE_TS),
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


def test_atom_replay_scrub(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1', [{ id: 'implementation', type: 'phase', handler: 'implementation', enabled: true }]);
        engine.loadHistory([
          { event_id: '1', type: 'phase_start', name: 'implementation', ts: '2026-04-21T00:00:00Z' },
          { event_id: '2', type: 'phase_done', name: 'implementation', ts: '2026-04-21T00:00:01Z' },
        ]);
        assert.equal(engine.snapshot().atoms.implementation.state, 'done');
        engine.scrubTo(0);
        assert.equal(engine.snapshot().atoms.implementation.state, 'active');
        engine.resumeLive();
        assert.equal(engine.snapshot().atoms.implementation.state, 'done');
        """,
    )


def test_cost_replay_and_budget_gate(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: '1',
            type: 'usage_recorded',
            step: 'architect',
            provider_name: 'openrouter',
            model: 'm',
            role: 'architect',
            usage: { input_tokens: 10, output_tokens: 5 },
            cost: { effective_cost: 0.25, provider_reported_cost: 0.25, estimated_cost: null, source: 'provider_reported' },
          },
          {
            event_id: '2',
            type: 'budget_gate_decided',
            gate_id: 'budget_run',
            decision: 'rejected',
            new_run_budget_usd: 10,
            budget_at_decision: { remaining_run_budget_usd: 7.5, remaining_phase_budget_usd: null },
          },
          {
            event_id: '3',
            type: 'usage_recorded',
            step: 'testing',
            usage: { input_tokens: 1 },
            cost: { effective_cost: null, provider_reported_cost: null, estimated_cost: null, source: 'unknown' },
          },
        ]);
        let cost = engine.snapshot().cost;
        assert.equal(cost.effectiveUsd, 0.25);
        assert.equal(cost.providerReportedUsd, 0.25);
        assert.equal(cost.unknownCostCount, 1);
        assert.equal(cost.remainingRunBudgetUsd, 7.5);
        assert.equal(cost.runHalted, true);
        engine.scrubTo(0);
        cost = engine.snapshot().cost;
        assert.equal(cost.effectiveUsd, 0.25);
        assert.equal(cost.remainingRunBudgetUsd, null);
        assert.equal(cost.runHalted, false);
        """,
    )


def test_loop_replay_repair_and_learn(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          { event_id: '1', type: 'loop_entered', step: 'testing', atom_id: 'testing', loop_stage: 'verify' },
          { event_id: '2', type: 'loop_repaired', step: 'testing', atom_id: 'testing', loop_stage: 'repair' },
          { event_id: '3', type: 'loop_entered', step: 'memory_refresh', atom_id: 'memory_refresh', loop_stage: 'learn', memory_refs: ['wakeup'] },
        ]);
        let loops = engine.snapshot().loops;
        assert.equal(loops.byAtom.testing.currentStage, 'repair');
        assert.equal(loops.byAtom.testing.repairCount, 1);
        assert.equal(loops.byAtom.memory_refresh.currentStage, 'learn');
        assert.deepEqual(loops.byAtom.memory_refresh.memoryRefs, ['wakeup']);
        engine.scrubTo(0);
        loops = engine.snapshot().loops;
        assert.equal(loops.byAtom.testing.currentStage, 'verify');
        assert.equal(loops.byAtom.testing.repairCount, 0);
        """,
    )


def test_replay_receives_live_history_without_moving_scrub(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1', [{ id: 'architect', type: 'phase', handler: 'architect', enabled: true }]);
        engine.loadHistory([
          { event_id: '1', type: 'phase_start', name: 'architect' },
          { event_id: '2', type: 'phase_done', name: 'architect' },
        ]);
        engine.scrubTo(0);
        assert.equal(engine.snapshot().replayIndex, 0);
        assert.equal(engine.snapshot().atoms.architect.state, 'active');
        assert.equal(engine.applyEvent({ event_id: '3', type: 'phase_error', name: 'architect' }), true);
        assert.equal(engine.snapshot().historyLength, 3);
        assert.equal(engine.snapshot().replayIndex, 0);
        assert.equal(engine.snapshot().atoms.architect.state, 'active');
        engine.resumeLive();
        assert.equal(engine.snapshot().atoms.architect.state, 'error');
        """,
    )
