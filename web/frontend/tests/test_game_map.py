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
    assert "next-step-sheet" in text
    assert "next-step-control" in text
    assert "openNextStepSheet" in text
    assert "goal-core-sheet" in text
    assert "goal-core-control" in text
    assert "openGoalCoreSheet" in text
    assert "renderGoalCoreSheet" in text
    assert "memory-core-sheet" in text
    assert "memory-core-control" in text
    assert "openMemorySheet" in text
    assert "renderMemorySheet" in text
    assert "memoryStatusCard" in text
    assert "memory-sync-control" in text
    assert "/memory/sync" in text
    assert "founding-team-brief" in text
    assert "founderCard" in text
    assert "object-lens-sheet" in text
    assert "renderObjectLens" in text
    assert "objectCommandStyle" in text
    assert "Produced" in text
    assert "Consumed" in text
    assert "story-lens-sheet" in text
    assert "story-lens-control" in text
    assert "renderStoryLens" in text
    assert "story-card" in text
    assert "storyDigestCard" in text
    assert "story-discussion-card" in text
    assert "story-highlight-card" in text
    assert "memoryProvenanceRefs" in text
    assert "storyAtomIdsForSnapshot" in text
    assert "setStoryFocus" in text
    assert "setLensDimmed" in text
    assert "focusGoalCore" in text
    assert "goal-core:body" in text
    assert "onSelectMemoryCore" in (ROOT / "web" / "frontend" / "src" / "game" / "SceneManager.ts").read_text()
    assert "memory-core:body" in (ROOT / "web" / "frontend" / "src" / "game" / "SceneManager.ts").read_text()
    assert "narrative-digest" in text
    assert "latestDigestPanel" in text
    assert "Recent story" in text
    assert "narrator-dialogue" in text
    assert "Run Narrator" in text
    assert "narrator-replay" in text
    assert "narrator-skip" in text
    assert "prefersReducedMotion" in text
    assert "discussion-log" in text
    assert "discussionPanel" in text
    assert "snapshot.nextStepPacket" in text
    assert "queuedIntents" in text
    assert "pendingIntents" in text
    assert "appliedIntents" in text
    assert "ignoredIntents" in text
    assert "intent-packet:" in text
    assert "syncIntentPacketSprites" in text
    assert "makeIntentPacketSprite" in text
    assert "intentStatusGlyph" in text
    assert "radial-action-ring" in text
    assert "compose-dock" in text
    assert "timeline-ribbon" in text
    assert "data-view-level" in text
    assert "setViewLevel" in text
    assert "<select" not in text
    assert "/intents" in text
    assert "client_intent_id" in text
    assert "newClientIntentId" in text
    assert "demo-card" in text
    assert "story-demo-rail" in text
    assert "object-demo-rail" in text
    assert "demoArtifactUrl" in text
    assert "storyDemoCard" in text
    assert "artifactPreviewCard" in text
    assert "story-preview-rail" in text
    assert "object-preview-rail" in text
    assert "preview-card" in text
    assert "preview-excerpt" in text


def test_demo_artifact_url_and_card_helpers(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';

        globalThis.document = {
          createElement: () => {
            const node = { textContent: '', get innerHTML() { return String(this.textContent).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); } };
            return node;
          },
        };

        const { demoArtifactUrl, storyDemoCard } = await import('__BUNDLE__');

        const viewport = { name: 'mobile', width: 393, height: 852 };
        const gif = { ref: '.orchestrator/demos/demo_abc123/demo.gif', kind: 'gif', sha256: 'hh', bytes: 10, testStatus: 'passed', viewport, eventId: 'e1' };
        const png = { ref: '.orchestrator/demos/demo_abc123/mobile.png', kind: 'screenshot', sha256: 'pp', bytes: 5, testStatus: 'passed', viewport, eventId: 'e2' };
        const demo = {
          demoId: 'demo_abc123',
          status: 'presented',
          adapter: 'playwright_web',
          confidence: 'explicit_playwright',
          reason: 'Maps should open on mobile',
          taskId: 'task-1',
          atomId: 'implementation',
          startCommand: 'npm run dev',
          testCommand: 'npx playwright test',
          specPath: 'demo/game-map.spec.ts',
          route: '/game',
          viewports: ['mobile'],
          capturePolicy: ['gif','trace'],
          viewport,
          artifacts: [gif, png],
          testStatus: 'passed',
          captureError: null,
          summaryRef: '.orchestrator/demos/demo_abc123/metadata.json',
          sourceRefs: ['src/game/Map.ts'],
          artifactRefs: [gif.ref, png.ref],
          wakeUpHash: 'abcdef1234567890',
          memoryRefs: ['mem-1'],
          lastEvent: null,
          raw: {},
        };

        const url = demoArtifactUrl('proj-1', demo, gif);
        assert.equal(url, '/api/projects/proj-1/demos/demo_abc123/demo.gif');

        const nested = { ...gif, ref: '.orchestrator/demos/demo_abc123/playwright-report/index.html' };
        const nestedUrl = demoArtifactUrl('proj-1', demo, nested);
        assert.equal(nestedUrl, '/api/projects/proj-1/demos/demo_abc123/playwright-report/index.html');

        const bare = { ...gif, ref: '' };
        assert.equal(demoArtifactUrl('proj-1', demo, bare), '');

        const html = storyDemoCard(demo, 'proj-1');
        assert.ok(html.includes('data-role="demo-card"'));
        assert.ok(html.includes('data-demo-id="demo_abc123"'));
        assert.ok(html.includes('data-demo-status="presented"'));
        assert.ok(html.includes('data-role="demo-thumb"'));
        assert.ok(html.includes('/api/projects/proj-1/demos/demo_abc123/demo.gif'));
        assert.ok(html.includes('Maps should open on mobile'));
        assert.ok(html.includes('Ready'));

        const failing = { ...demo, status: 'failed', captureError: 'boom: selector missing', artifacts: [] };
        const failHtml = storyDemoCard(failing, 'proj-1');
        assert.ok(failHtml.includes('data-demo-status="failed"'));
        assert.ok(failHtml.includes('boom: selector missing'));
        assert.ok(!failHtml.includes('data-role="demo-thumb"'));
        """,
        include_three=True,
    )


def test_artifact_preview_card_helper(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';

        globalThis.document = {
          createElement: () => {
            const node = { textContent: '', get innerHTML() { return String(this.textContent).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); } };
            return node;
          },
        };

        const { artifactPreviewCard } = await import('__BUNDLE__');

        const textPreview = {
          eventId: 'evt-1',
          artifactRef: 'sprint-plan.md',
          producingAtomId: 'architect_plan',
          projectId: 'proj-1',
          hash: '0123456789abcdef0123456789abcdef',
          bytes: 4096,
          mime: 'text/markdown',
          excerpt: '# Sprint\\n<script>alert(1)</script>',
          excerptKind: 'text_head',
          truncated: true,
          triggerEventId: 'trigger-xyz',
          sourceRefs: ['qwendea.md'],
          wakeUpHash: 'abc',
          memoryRefs: [],
          ts: 0,
        };

        const html = artifactPreviewCard(textPreview);
        assert.ok(html.includes('data-role="preview-card"'));
        assert.ok(html.includes('data-preview-ref="sprint-plan.md"'));
        assert.ok(html.includes('data-preview-atom="architect_plan"'));
        assert.ok(html.includes('data-excerpt-kind="text_head"'));
        assert.ok(html.includes('4.0 KiB'));
        assert.ok(html.includes('#0123456789ab'));
        assert.ok(html.includes('atom: architect_plan'));
        assert.ok(html.includes('text/markdown'));
        assert.ok(html.includes('qwendea.md'));
        assert.ok(html.includes('Truncated'));
        assert.ok(html.includes('&lt;script&gt;'), 'excerpt must be HTML-escaped');
        assert.ok(!html.includes('<script>alert'));

        const binary = {
          ...textPreview,
          artifactRef: 'image.png',
          excerpt: '[binary artifact: image.png (2048 bytes)]',
          excerptKind: 'binary_placeholder',
          mime: 'image/png',
          truncated: false,
        };
        const binaryHtml = artifactPreviewCard(binary);
        assert.ok(binaryHtml.includes('data-excerpt-kind="binary_placeholder"'));
        assert.ok(binaryHtml.includes('binary artifact: image.png'));
        assert.ok(!binaryHtml.includes('Truncated'));

        const untruncated = { ...textPreview, excerpt: 'short', truncated: false, excerptKind: 'text_tail' };
        const untruncatedHtml = artifactPreviewCard(untruncated);
        assert.ok(!untruncatedHtml.includes('Truncated'));
        assert.ok(untruncatedHtml.includes('data-excerpt-kind="text_tail"'));

        const bytesSmall = artifactPreviewCard({ ...textPreview, bytes: 500 });
        assert.ok(bytesSmall.includes('500 B'));

        const bytesMb = artifactPreviewCard({ ...textPreview, bytes: 3 * 1024 * 1024 });
        assert.ok(bytesMb.includes('3.0 MiB'));
        """,
        include_three=True,
    )


def test_memory_status_card_helper(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';

        globalThis.document = {
          createElement: () => {
            const node = { textContent: '', get innerHTML() { return String(this.textContent).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); } };
            return node;
          },
        };

        const { memoryStatusCard } = await import('__BUNDLE__');

        const snapshot = {
          memPalaceStatus: {
            available: true,
            initialized: true,
            wing: 'project-demo',
            cached_wakeup: 'Wake <packet>\\nNext thing',
            last_search: 'Search <result>',
            wakeUpHash: 'abcdef1234567890',
            wakeUpBytes: 2048,
            memoryRefs: ['.orchestrator/memory/wake-up.md'],
            artifactRefs: ['.orchestrator/memory/wake-up.md'],
            error: null,
            lastEvent: null,
          },
          memoryEvents: [
            {
              type: 'memory_refreshed',
              eventId: 'mem-1',
              available: true,
              initialized: true,
              wing: 'project-demo',
              cachedWakeup: 'Wake <packet>',
              lastSearch: '',
              wakeUpHash: 'abcdef1234567890',
              wakeUpBytes: 2048,
              memoryRefs: ['.orchestrator/memory/wake-up.md'],
              artifactRefs: ['.orchestrator/memory/wake-up.md'],
              error: null,
              query: null,
              room: null,
              results: null,
              ts: 0,
              lastEvent: null,
            },
            {
              type: 'memory_search_completed',
              eventId: 'mem-2',
              available: true,
              initialized: true,
              wing: 'project-demo',
              cachedWakeup: 'Wake <packet>',
              lastSearch: 'Search <result>',
              wakeUpHash: 'abcdef1234567890',
              wakeUpBytes: 2048,
              memoryRefs: ['.orchestrator/memory/wake-up.md'],
              artifactRefs: ['.orchestrator/memory/wake-up.md'],
              error: null,
              query: 'founding team',
              room: 'project',
              results: 2,
              ts: 1,
              lastEvent: null,
            },
          ],
        };

        const html = memoryStatusCard(snapshot);
        assert.ok(html.includes('data-role="memory-status-card"'));
        assert.ok(html.includes('data-role="memory-wakeup-preview"'));
        assert.ok(html.includes('data-role="memory-last-search"'));
        assert.ok(html.includes('data-role="memory-event-rail"'));
        assert.ok(html.includes('project-demo'));
        assert.ok(html.includes('abcdef1234567890'));
        assert.ok(html.includes('2.0 KiB'));
        assert.ok(html.includes('&lt;packet&gt;'));
        assert.ok(html.includes('query: founding team'));
        assert.ok(!html.includes('<packet>'));
        """,
        include_three=True,
    )


def test_story_provenance_cards_show_memory_refs(tmp_path: Path) -> None:
    run_script(
        tmp_path,
        GAME_SHELL_TS,
        """
        import assert from 'node:assert/strict';

        globalThis.document = {
          createElement: () => {
            const node = { textContent: '', get innerHTML() { return String(this.textContent).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;'); } };
            return node;
          },
        };

        const { storyDigestCard, discussionEntryCard, discussionHighlightCard } = await import('__BUNDLE__');

        const baseEvent = { type: 'x', event_id: 'evt-1', ts: 0 };
        const digestHtml = storyDigestCard({
          digestId: 'digest-1',
          title: 'Memory shaped digest',
          summary: 'Claim from <wake-up>',
          highlights: [{ text: 'Highlight one', sourceRefs: ['event:evt-1'] }],
          risks: [],
          openQuestions: [],
          nextStepHint: 'coder',
          sourceEventIds: ['evt-1'],
          artifactRefs: ['artifact:REVIEW.md'],
          window: { event_count: 1 },
          wakeUpHash: 'abcdef1234567890',
          memoryRefs: ['.orchestrator/memory/wake-up.md'],
          lastEvent: baseEvent,
          raw: {},
        });
        assert.ok(digestHtml.includes('memory: .orchestrator/memory/wake-up.md'));
        assert.ok(digestHtml.includes('wake: abcdef123456'));
        assert.ok(digestHtml.includes('&lt;wake-up&gt;'));
        assert.ok(!digestHtml.includes('<wake-up>'));

        const entryHtml = discussionEntryCard({
          discussionEntryId: 'disc-1',
          speaker: 'Operator <One>',
          entryType: 'consult_persona_statement',
          atomId: 'review',
          text: 'Check memory claim',
          sourceRefs: ['event:evt-2'],
          artifactRefs: ['artifact:FOUNDING_TEAM.json'],
          metadata: {},
          wakeUpHash: 'fedcba9876543210',
          memoryRefs: ['.orchestrator/memory/last-search.txt'],
          lastEvent: baseEvent,
          raw: {},
        });
        assert.ok(entryHtml.includes('data-role="story-discussion-card"'));
        assert.ok(entryHtml.includes('memory: .orchestrator/memory/last-search.txt'));
        assert.ok(entryHtml.includes('wake: fedcba987654'));
        assert.ok(entryHtml.includes('Operator &lt;One&gt;'));

        const highlightHtml = discussionHighlightCard({
          discussionHighlightId: 'hl-1',
          highlightType: 'source_backed_convergence',
          atomId: 'review',
          text: 'Consensus cites memory',
          sourceRefs: ['entry:disc-1'],
          artifactRefs: [],
          wakeUpHash: '1234567890abcdef',
          memoryRefs: ['.orchestrator/memory/wake-up.md'],
          lastEvent: baseEvent,
          raw: {},
        });
        assert.ok(highlightHtml.includes('data-role="story-highlight-card"'));
        assert.ok(highlightHtml.includes('source backed convergence'));
        assert.ok(highlightHtml.includes('memory: .orchestrator/memory/wake-up.md'));
        assert.ok(highlightHtml.includes('wake: 1234567890ab'));
        """,
        include_three=True,
    )
