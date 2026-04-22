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


def test_unknown_event_type_is_ignored_by_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1', [{ id: 'implementation', type: 'phase', handler: 'implementation', enabled: true }]);
        engine.loadHistory([
          { event_id: '1', type: 'typo_event', name: 'implementation', ts: '2026-04-21T00:00:00Z' },
        ]);
        assert.equal(engine.snapshot().atoms.implementation.state, 'idle');
        assert.equal(engine.snapshot().historyLength, 1);
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


def test_next_step_packet_replay_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: '1',
            type: 'next_step_packet_created',
            packet_id: 'next_1',
            step: 'memory_refresh',
            memory_refs: ['.orchestrator/memory/wake-up.md'],
            packet: {
              packet_id: 'next_1',
              step: 'memory_refresh',
              title: 'Memory',
              role: 'memory_refresh',
              objective: 'Refresh memory.',
              why_now: 'It is first.',
              inputs: [{ kind: 'memory', ref: '.orchestrator/memory/wake-up.md' }],
              queued_intents: [{ client_intent_id: 'intent-1', kind: 'interject' }],
              context_preview: ['Memory wake-up hash: abc'],
              intervention_options: ['interject'],
              source_refs: ['workflow:memory_refresh', 'memory:.orchestrator/memory/wake-up.md'],
            },
          },
          {
            event_id: '2',
            type: 'next_step_packet_created',
            packet_id: 'next_2',
            step: 'persona_forum',
            packet: {
              packet_id: 'next_2',
              step: 'persona_forum',
              title: 'Team',
              role: 'persona_forum',
              objective: 'Shape team.',
              why_now: 'Memory completed.',
              inputs: [],
              context_preview: [],
              intervention_options: ['intercept'],
              source_refs: ['workflow:persona_forum'],
            },
          },
        ]);
        assert.equal(engine.snapshot().nextStepPacket.step, 'persona_forum');
        engine.scrubTo(0);
        const packet = engine.snapshot().nextStepPacket;
        assert.equal(packet.step, 'memory_refresh');
        assert.deepEqual(packet.memoryRefs, ['.orchestrator/memory/wake-up.md']);
        assert.equal(packet.queuedIntents[0].client_intent_id, 'intent-1');
        assert.equal(packet.contextPreview[0], 'Memory wake-up hash: abc');
        """,
    )


def test_operator_intent_lifecycle_replay_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: 'evt-intent-1',
            type: 'operator_intent',
            client_intent_id: 'intent-1',
            kind: 'interject',
            atom_id: 'implementation',
            payload: { instruction: 'Use the lifecycle fold.' },
            source_refs: ['event:evt-intent-1'],
          },
          {
            event_id: 'evt-applied-1',
            type: 'operator_intent_applied',
            client_intent_id: 'intent-1',
            intent_event_id: 'evt-intent-1',
            kind: 'interject',
            atom_id: 'implementation',
            step: 'implementation',
            applied_to: 'prompt_context',
            artifact_refs: ['prompt:implementation'],
            source_refs: ['intent:intent-1'],
          },
          {
            event_id: 'evt-intent-2',
            type: 'operator_intent',
            client_intent_id: 'intent-2',
            kind: 'note',
            atom_id: 'testing',
            payload: { instruction: 'Leave this as a note.' },
          },
          {
            event_id: 'evt-ignored-2',
            type: 'operator_intent_ignored',
            client_intent_id: 'intent-2',
            intent_event_id: 'evt-intent-2',
            kind: 'note',
            atom_id: 'testing',
            step: 'testing',
            reason: 'unsupported_kind',
            source_refs: ['intent:intent-2'],
          },
        ]);
        let snapshot = engine.snapshot();
        assert.deepEqual(Object.keys(snapshot.pendingIntents), []);
        assert.equal(snapshot.appliedIntents['intent-1'].appliedTo, 'prompt_context');
        assert.equal(snapshot.appliedIntents['intent-1'].artifactRefs[0], 'prompt:implementation');
        assert.equal(snapshot.ignoredIntents['intent-2'].reason, 'unsupported_kind');

        engine.scrubTo(0);
        snapshot = engine.snapshot();
        assert.equal(snapshot.pendingIntents['intent-1'].status, 'queued');
        assert.deepEqual(Object.keys(snapshot.appliedIntents), []);
        assert.deepEqual(Object.keys(snapshot.ignoredIntents), []);

        engine.scrubTo(1);
        snapshot = engine.snapshot();
        assert.deepEqual(Object.keys(snapshot.pendingIntents), []);
        assert.equal(snapshot.appliedIntents['intent-1'].status, 'applied');
        """,
    )


def test_pending_intent_attaches_to_current_next_step_packet(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: 'packet-1',
            type: 'next_step_packet_created',
            packet: {
              packet_id: 'next_1',
              step: 'implementation',
              title: 'Build',
              role: 'coder',
              objective: 'Build the slice.',
              why_now: 'It is next.',
              inputs: [],
              queued_intents: [{ client_intent_id: 'intent-existing', kind: 'interject' }],
              context_preview: [],
              intervention_options: ['interject'],
              source_refs: ['workflow:implementation'],
            },
          },
          {
            event_id: 'intent-event',
            type: 'operator_intent',
            client_intent_id: 'intent-live',
            kind: 'interject',
            atom_id: 'implementation',
            payload: { instruction: 'Include lifecycle state.' },
          },
          {
            event_id: 'intent-global',
            type: 'operator_intent',
            client_intent_id: 'intent-global',
            kind: 'intercept',
            atom_id: null,
            payload: { instruction: 'Global steering.' },
          },
          {
            event_id: 'intent-other',
            type: 'operator_intent',
            client_intent_id: 'intent-other',
            kind: 'interject',
            atom_id: 'testing',
            payload: { instruction: 'Not for this step.' },
          },
        ]);
        const queued = engine.snapshot().nextStepPacket.queuedIntents.map((intent) => intent.client_intent_id);
        assert.deepEqual(queued, ['intent-existing', 'intent-live', 'intent-global']);
        engine.scrubTo(0);
        assert.deepEqual(
          engine.snapshot().nextStepPacket.queuedIntents.map((intent) => intent.client_intent_id),
          ['intent-existing'],
        );
        """,
    )


def test_narrative_digest_replay_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: 'evt-digest-1',
            type: 'narrative_digest_created',
            digest_id: 'dwa_1',
            title: 'Memory completed',
            summary: 'Recent ledger window: 1 phase_done. Next: Team.',
            highlights: [{ text: 'Completed memory_refresh.', source_refs: ['event:evt-phase-1'] }],
            risks: [],
            open_questions: [],
            next_step_hint: 'Team',
            source_event_ids: ['evt-phase-1'],
            artifact_refs: ['.orchestrator/narrative/digests/dwa_1.json'],
            window: { from_event_id: 'evt-phase-1', to_event_id: 'evt-phase-1', event_count: 1 },
          },
          {
            event_id: 'evt-digest-2',
            type: 'narrative_digest_created',
            digest: {
              digest_id: 'dwa_2',
              title: 'Team completed',
              summary: 'Recent ledger window: 1 phase_done. Next: Architect.',
              highlights: [{ text: 'Completed persona_forum.', source_refs: ['event:evt-phase-2'] }],
              risks: ['Intent ignored: unsupported_kind.'],
              open_questions: ['Does the queued operator intent need a terminal applied or ignored outcome?'],
              next_step_hint: 'Architect',
              source_event_ids: ['evt-phase-2'],
              artifact_refs: ['.orchestrator/narrative/digests/dwa_2.json'],
              window: { from_event_id: 'evt-phase-2', to_event_id: 'evt-phase-2', event_count: 1 },
            },
          },
        ]);
        let snapshot = engine.snapshot();
        assert.equal(snapshot.digests.length, 2);
        assert.equal(snapshot.latestDigest.digestId, 'dwa_2');
        assert.equal(snapshot.latestDigest.highlights[0].sourceRefs[0], 'event:evt-phase-2');
        assert.equal(snapshot.latestDigest.risks[0], 'Intent ignored: unsupported_kind.');

        engine.scrubTo(0);
        snapshot = engine.snapshot();
        assert.equal(snapshot.digests.length, 1);
        assert.equal(snapshot.latestDigest.digestId, 'dwa_1');
        assert.equal(snapshot.latestDigest.nextStepHint, 'Team');
        """,
    )


def test_discussion_replay_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: 'evt-disc-1',
            type: 'discussion_entry_created',
            entry: {
              discussion_entry_id: 'disc_1',
              speaker: 'operator',
              entry_type: 'operator_note',
              atom_id: 'testing',
              text: 'Keep evidence visible.',
              source_refs: ['event:evt-intent-1'],
              artifact_refs: ['.orchestrator/control/intents.jsonl'],
              metadata: { client_intent_id: 'intent-1' },
            },
          },
          {
            event_id: 'evt-high-1',
            type: 'discussion_highlight_created',
            highlight: {
              discussion_highlight_id: 'high_1',
              highlight_type: 'persona_forum',
              atom_id: 'persona_forum',
              text: 'Founding team discussion captured 4 persona statements.',
              source_refs: ['entry:disc_1'],
              artifact_refs: ['PERSONA_FORUM.md'],
            },
          },
        ]);
        let snapshot = engine.snapshot();
        assert.equal(snapshot.discussion.length, 1);
        assert.equal(snapshot.discussion[0].speaker, 'operator');
        assert.equal(snapshot.discussion[0].metadata.client_intent_id, 'intent-1');
        assert.equal(snapshot.discussionHighlights[0].sourceRefs[0], 'entry:disc_1');

        engine.scrubTo(0);
        snapshot = engine.snapshot();
        assert.equal(snapshot.discussion.length, 1);
        assert.equal(snapshot.discussionHighlights.length, 0);
        """,
    )


def test_narrative_and_discussion_provenance_fold(tmp_path: Path) -> None:
    run_engine_script(
        tmp_path,
        """
        import assert from 'node:assert/strict';
        import { EventEngine } from '__BUNDLE__';
        const engine = new EventEngine('p1');
        engine.loadHistory([
          {
            event_id: 'evt-digest-prov',
            type: 'narrative_digest_created',
            wake_up_hash: 'hash-1',
            memory_refs: ['.orchestrator/memory/wake-up.md'],
            digest: {
              digest_id: 'dwa_prov',
              title: 'Digest with provenance',
              summary: 'Summary.',
              highlights: [{ text: 'Hi.', source_refs: ['event:evt-phase-1'] }],
              risks: [],
              open_questions: [],
              next_step_hint: null,
              source_event_ids: ['evt-phase-1'],
              artifact_refs: ['.orchestrator/narrative/digests/dwa_prov.json'],
              window: { from_event_id: 'evt-phase-1', to_event_id: 'evt-phase-1', event_count: 1 },
              wake_up_hash: 'hash-1',
              memory_refs: ['.orchestrator/memory/wake-up.md'],
            },
          },
          {
            event_id: 'evt-disc-prov',
            type: 'discussion_entry_created',
            wake_up_hash: 'hash-1',
            memory_refs: ['.orchestrator/memory/wake-up.md'],
            entry: {
              discussion_entry_id: 'disc_prov',
              speaker: 'Founder',
              entry_type: 'persona_statement',
              atom_id: 'persona_forum',
              text: 'Keep scope sharp.',
              source_refs: ['artifact:FOUNDING_TEAM.json'],
              artifact_refs: ['FOUNDING_TEAM.json'],
              metadata: {},
              wake_up_hash: 'hash-1',
              memory_refs: ['.orchestrator/memory/wake-up.md'],
            },
          },
          {
            event_id: 'evt-high-prov',
            type: 'discussion_highlight_created',
            wake_up_hash: 'hash-1',
            memory_refs: ['.orchestrator/memory/wake-up.md'],
            highlight: {
              discussion_highlight_id: 'high_prov',
              highlight_type: 'persona_forum',
              atom_id: 'persona_forum',
              text: 'Founding team convened.',
              source_refs: ['entry:disc_prov'],
              artifact_refs: ['PERSONA_FORUM.md'],
              wake_up_hash: 'hash-1',
              memory_refs: ['.orchestrator/memory/wake-up.md'],
            },
          },
        ]);
        const snapshot = engine.snapshot();
        assert.equal(snapshot.latestDigest.wakeUpHash, 'hash-1');
        assert.deepEqual(snapshot.latestDigest.memoryRefs, ['.orchestrator/memory/wake-up.md']);
        assert.equal(snapshot.discussion[0].wakeUpHash, 'hash-1');
        assert.deepEqual(snapshot.discussion[0].memoryRefs, ['.orchestrator/memory/wake-up.md']);
        assert.equal(snapshot.discussionHighlights[0].wakeUpHash, 'hash-1');
        assert.deepEqual(snapshot.discussionHighlights[0].memoryRefs, ['.orchestrator/memory/wake-up.md']);
        """,
    )
